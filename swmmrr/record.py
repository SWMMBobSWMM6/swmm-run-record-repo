"""record.py - run one engine on one model and write its run record (schema swmm-run-record/1).

A run record says what ran (the engine, its build fingerprint and its verification), on what (the model and every
file it reads, by SHA-256), how it ended (status, exit code, the engine's own ERROR and WARNING lines, whether it
reached the model's end time), and what it produced (the .rpt and .out by SHA-256, the units, the continuity tables,
the routing time-step summary, the peak of every reporting variable for every object, and any time series asked
for). The engine's own .rpt and .out are kept beside the record. Every engine is run the same way: from the model's
own folder, as COMMAND model.inp report.rpt output.out.

Written by Claude (Anthropic) for Robert Dickinson; see AI-USE.md.
"""
import datetime as dt
import hashlib
import json
import math
import os
import resource
import signal
import subprocess
import time

from . import engines, inpfile, outfile, rptfile

SCHEMA = 'swmm-run-record/1'
TOOL = dict(name='swmmrr', version='1.0.1')
EPOCH = dt.datetime(1899, 12, 30)                     # SWMM keeps dates as days since 12/30/1899


def swmm_date(d):
    """A SWMM date (days, as a double) as an ISO 8601 string, to the nearest second."""
    return (EPOCH + dt.timedelta(seconds=round(d * 86400.0))).isoformat()


def _inp_datetime(date, clock):
    for fmt in ('%m/%d/%Y %H:%M:%S', '%m/%d/%Y %H:%M'):
        try:
            return dt.datetime.strptime('%s %s' % (date, clock or '00:00:00'), fmt)
        except (ValueError, TypeError):
            pass
    return None


UNITS = {'US': dict(depth='ft', head='ft', length='ft', velocity='ft/s', volume='ft3', area='acre',
                    rainfall='in/hr', temperature='deg F'),
         'SI': dict(depth='m', head='m', length='m', velocity='m/s', volume='m3', area='ha',
                    rainfall='mm/hr', temperature='deg C')}


def _peaks(o):
    """The maximum (and for link flow also the minimum) of every reporting variable of every object, with the time
    of the first period that reaches it, read from the .out file in one pass over the periods."""
    nsv, nnv, nlv, nyv = o.nsv, o.nnv, o.nlv, o.nyv
    nvals = o.nsub * nsv + o.nnode * nnv + o.nlink * nlv + nyv
    hi = [float('-inf')] * nvals
    hik = [0] * nvals
    lo = [float('inf')] * nvals
    lok = [0] * nvals
    for k in range(o.nperiods):
        v = o.period_values(k)
        for i in range(nvals):
            x = v[i]
            if x > hi[i]:
                hi[i] = x
                hik[i] = k
            if x < lo[i]:
                lo[i] = x
                lok[i] = k
    dates = o.dates()

    def t(k):
        return swmm_date(dates[k]) if dates else None

    out = dict(subcatchments={}, nodes={}, links={}, system={})
    base = 0
    for kind, names, nv, key in (('sub', o.subcatchments, nsv, 'subcatchments'), ('node', o.nodes, nnv, 'nodes'),
                                 ('link', o.links, nlv, 'links')):
        vn = o.var_names(kind)
        for j, name in enumerate(names):
            d = {}
            for q in range(nv):
                i = base + j * nv + q
                d['max_' + vn[q]] = hi[i]
                d['max_' + vn[q] + '_time'] = t(hik[i])
                if kind == 'link' and vn[q] == 'flow':
                    d['min_flow'] = lo[i]
                    d['min_flow_time'] = t(lok[i])
            if kind == 'node':
                d['type'] = o.node_type(j)
            elif kind == 'link':
                d['type'] = o.link_type(j)
            out[key][name] = d
        base += len(names) * nv
    for q, name in enumerate(o.var_names('sys')):
        i = base + q
        out['system'][name] = dict(max=hi[i], max_time=t(hik[i]), min=lo[i])
    return out


def _summary(pk, o):
    """The headline numbers a reader looks at first, each with the object that holds it."""
    def top(table, var):
        best = None
        for name, d in table.items():
            v = d.get(var)
            if v is not None and (best is None or v > best[1]):
                best = (name, v, d.get(var + '_time'))
        if best is None:
            return None
        if best[1] <= 0 and var in ('max_flooding', 'max_capacity'):
            return dict(id=None, value=best[1], time=None)          # nothing flooded or flowed: no holder to name
        return dict(id=best[0], value=best[1], time=best[2])

    s = dict(nodes={}, links={}, subcatchments={})
    if pk['nodes']:
        for var in ('max_depth', 'max_total_inflow', 'max_flooding'):
            s['nodes'][var] = top(pk['nodes'], var)
        s['nodes']['flooded_nodes'] = sum(1 for d in pk['nodes'].values() if d.get('max_flooding', 0) > 0)
    if pk['links']:
        for var in ('max_flow', 'max_velocity', 'max_capacity'):
            s['links'][var] = top(pk['links'], var)
        s['links']['links_reversing'] = sum(1 for d in pk['links'].values()
                                            if d.get('min_flow', 0) < 0 < d.get('max_flow', 0))
        s['links']['links_full'] = sum(1 for d in pk['links'].values() if d.get('max_capacity', 0) >= 1.0)
    if pk['subcatchments']:
        s['subcatchments']['max_runoff'] = top(pk['subcatchments'], 'max_runoff')
    return s


def _out_sections(o):
    """The parts of a record that come from the .out file alone and from nothing else about the run: the units,
    the objects, the summary and the peaks. run() writes them; reread() derives them again from the same file."""
    system = o.unit_system
    nt, lt = {}, {}
    for j in range(o.nnode):
        nt[o.node_type(j)] = nt.get(o.node_type(j), 0) + 1
    for j in range(o.nlink):
        lt[o.link_type(j)] = lt.get(o.link_type(j), 0) + 1
    pk = _peaks(o) if o.nperiods else dict(subcatchments={}, nodes={}, links={}, system={})
    return dict(units=dict(flow=o.flow_units, system=system, **UNITS[system]),
                objects=dict(subcatchments=o.nsub, nodes=o.nnode, links=o.nlink, pollutants=o.pollutants,
                             node_types=nt, link_types=lt,
                             variables={k: o.var_names(k) for k in ('sub', 'node', 'link', 'sys')}),
                summary=_summary(pk, o), peaks=pk)


def _differences(old, new, path=''):
    """JSON paths at which two values differ."""
    if isinstance(old, dict) and isinstance(new, dict):
        out = []
        for k in list(old) + [k for k in new if k not in old]:
            if k not in old or k not in new:
                out.append(path + k)
            else:
                out += _differences(old[k], new[k], path + k + '.')
        return out
    return [] if old == new else [path.rstrip('.')]


def reread(record_path, out_path, reason):
    """Derive a record's .out sections again from its .out file, with the reader as it is now.

    For a record made by a reader that has since been corrected. Nothing is run. The file must be the one the
    record names: its SHA-256 has to equal files.out.sha256, or nothing is changed. Only the sections that come
    from the .out alone (units, objects, summary, peaks) are derived again; what ran, on what, how it ended and
    when stay as recorded. Every changed value is counted in a new entry of the record's "corrections" list, so a
    record that was changed after it was made says so.

    Returns (record, changed) where changed maps each kind of path (object names replaced by *) to a count; an
    empty map means the record already agreed with the reader and was left alone."""
    with open(record_path) as fh:
        rec = json.load(fh)
    named = (rec.get('files') or {}).get('out', {}).get('sha256')
    if not named:
        raise ValueError('%s names no .out file: there is nothing to read again' % record_path)
    have = inpfile.sha256_file(out_path)
    if have != named:
        raise ValueError('%s is not the file this record was made from: its SHA-256 is %s, the record names %s'
                         % (out_path, have, named))
    new = json.loads(json.dumps(clean(_out_sections(outfile.OutFile(out_path))), allow_nan=False))
    changed = {}
    names = {'peaks.' + kind + '.': set((rec.get('peaks') or {}).get(kind, {})) | set(new['peaks'].get(kind, {}))
             for kind in ('subcatchments', 'nodes', 'links')}
    for section, value in new.items():
        for path in _differences(rec.get(section, {}), value, section + '.'):
            for prefix, ids in names.items():        # peaks.nodes.J1.type -> peaks.nodes.*.type
                if path.startswith(prefix):
                    rest = path[len(prefix):]
                    oid = max((i for i in ids if rest == i or rest.startswith(i + '.')), key=len, default=None)
                    if oid is not None:
                        path = prefix + '*' + rest[len(oid):]
                    break
            changed[path] = changed.get(path, 0) + 1
    if not changed:
        return rec, changed
    for section, value in new.items():
        rec[section] = value
    rec.setdefault('corrections', []).append(dict(
        date=dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds'), tool=TOOL, reason=reason,
        method='reread: units, objects, summary and peaks derived again from the .out file; nothing was run',
        out_sha256=have, changed=dict(sorted(changed.items()))))
    with open(record_path, 'w') as fh:
        json.dump(clean(rec), fh, indent=1, allow_nan=False)
    return rec, changed


def _series(o, specs):
    """Time series asked for as KIND:ID:VARIABLE (kind sub, node, link or sys; sys takes no id)."""
    lists = {'sub': o.subcatchments, 'node': o.nodes, 'link': o.links}
    out = []
    for spec in specs or []:
        kind, oid, var = (spec.split(':') + ['', ''])[:3]
        item = dict(kind=kind, id=oid or None, variable=var, values=None)
        if kind not in ('sub', 'node', 'link', 'sys'):
            item['note'] = 'unknown kind %r (use sub, node, link or sys)' % kind
        elif var not in o.var_names(kind):
            item['note'] = 'no variable %r for %s (this file has: %s)' % (var, kind, ', '.join(o.var_names(kind)))
        elif kind != 'sys' and oid not in lists[kind]:
            item['note'] = 'no %s named %r in this output file' % (kind, oid)
        else:
            idx = 0 if kind == 'sys' else lists[kind].index(oid)
            item['values'] = o.series(kind, idx, o.var_names(kind).index(var))
        out.append(item)
    return out


def run(engine_id, inp, workdir, timeout=3600.0, series=None, reg=None):
    """Run ENGINE_ID on INP, keep its files in WORKDIR, and return (and write) the run record."""
    e, reg = engines.get(engine_id, reg)
    os.makedirs(workdir, exist_ok=True)
    workdir = os.path.abspath(workdir)
    inp = os.path.abspath(inp)
    rpt, out = os.path.join(workdir, 'run.rpt'), os.path.join(workdir, 'run.out')
    for p in (rpt, out):
        if os.path.exists(p):
            os.remove(p)
    rec = dict(schema=SCHEMA, created=dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds'), tool=TOOL)
    cmd = engines.command(e, reg)
    why = engines.available(e, reg)
    rec['engine'] = dict(id=e['id'], family=e['family'], language=e['language'], role=e['role'], name=e['name'],
                         repo=e['repo'], pinned=e.get('pinned'), command=cmd, env=e.get('env', {}),
                         capabilities=e['capabilities'], verification=e.get('verification', []),
                         fingerprint=engines.fingerprint(e, reg) if not why else None)
    rec['model'] = inpfile.read(inp)
    if why:
        rec['run'] = dict(status='not_run', reason=why)
        _write(rec, workdir)
        return rec
    env = dict(os.environ)
    env.update(e.get('env', {}))
    r0 = resource.getrusage(resource.RUSAGE_CHILDREN)
    t0 = time.monotonic()
    timed_out = False
    with open(os.path.join(workdir, 'stdout.txt'), 'wb') as so, open(os.path.join(workdir, 'stderr.txt'), 'wb') as se:
        p = subprocess.Popen(cmd + [os.path.basename(inp), rpt, out], cwd=os.path.dirname(inp), stdout=so, stderr=se,
                             env=env, start_new_session=True)
        try:
            rc = p.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            os.killpg(p.pid, signal.SIGKILL)
            rc = p.wait()
    wall = time.monotonic() - t0
    r1 = resource.getrusage(resource.RUSAGE_CHILDREN)
    cpu = (r1.ru_utime - r0.ru_utime) + (r1.ru_stime - r0.ru_stime)
    with open(os.path.join(workdir, 'stderr.txt'), 'rb') as fh:
        stderr_tail = fh.read()[-2000:].decode('utf-8', 'replace')
    run_ = dict(exit_code=rc if rc >= 0 else 128 - rc, signal=-rc if rc < 0 else None, wall_seconds=round(wall, 3),
                cpu_seconds=round(cpu, 3), timeout_seconds=timeout, stderr_tail=stderr_tail or None)
    files = {}
    rp = None
    if os.path.isfile(rpt):
        rp = rptfile.parse(rpt)
        with open(rpt, 'r', encoding='latin-1') as fh:
            stripped = rptfile.strip_clock(fh.read()).encode('latin-1')
        files['rpt'] = dict(path=rpt, bytes=os.path.getsize(rpt), sha256=inpfile.sha256_file(rpt),
                            sha256_without_clock=hashlib.sha256(stripped).hexdigest())
        run_.update(errors=rp['errors'], warnings=rp['warnings'], warning_counts=rp['warning_counts'],
                    banner=rp['banner'])
    else:
        run_.update(errors=[], warnings=[], warning_counts={}, banner=None)
    o = None
    if os.path.isfile(out) and os.path.getsize(out) > 0:
        files['out'] = dict(path=out, bytes=os.path.getsize(out), sha256=inpfile.sha256_file(out))
        try:
            o = outfile.OutFile(out)
            files['out'].update(version=o.version, error_code=o.error_code, results_sha256=o.results_sha256())
        except ValueError as ex:
            files['out']['unreadable'] = str(ex)
    rec['files'] = files
    # how it ended
    if timed_out:
        status = 'timeout'
    elif run_['errors']:
        status = 'error'
    elif run_['exit_code'] != 0:
        status = 'crashed'
    elif o is None or o.error_code != 0:
        status = 'incomplete'
    else:
        status = 'completed'
    run_['status'] = status
    if not timed_out:
        run_['exit_code_agrees_with_report'] = (run_['exit_code'] != 0) == bool(run_['errors'])
    opts = rec['model']['options']
    end = _inp_datetime(opts.get('END_DATE'), opts.get('END_TIME'))
    rec['time'] = dict(model_start=(_inp_datetime(opts.get('START_DATE'), opts.get('START_TIME')) or None) and
                       _inp_datetime(opts.get('START_DATE'), opts.get('START_TIME')).isoformat(),
                       model_end=end.isoformat() if end else None)
    if o is not None:
        dates = o.dates()
        rec['time'].update(output_start=swmm_date(o.start_date), report_step_seconds=o.report_step,
                           periods=o.nperiods, first_report=swmm_date(dates[0]) if dates else None,
                           last_report=swmm_date(dates[-1]) if dates else None)
        if end and dates:
            last = EPOCH + dt.timedelta(seconds=round(dates[-1] * 86400.0))
            rec['time']['reached_end'] = (end - last).total_seconds() < o.report_step
            if status == 'completed' and not rec['time']['reached_end']:
                run_['status'] = 'incomplete'
        rec.update(_out_sections(o))
        if series:
            rec['series'] = dict(dates=[swmm_date(d) for d in dates], items=_series(o, series))
    rec['run'] = run_
    rec['continuity'] = rp['continuity'] if rp else {}
    rec['time_steps'] = rp['time_steps'] if rp else {}
    _write(rec, workdir)
    return rec


def clean(x):
    """JSON has no NaN or infinity: such a value is written as the string "NaN", "Infinity" or "-Infinity"."""
    if isinstance(x, float) and not math.isfinite(x):
        return 'NaN' if math.isnan(x) else ('Infinity' if x > 0 else '-Infinity')
    if isinstance(x, dict):
        return {k: clean(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [clean(v) for v in x]
    return x


def _write(rec, workdir):
    with open(os.path.join(workdir, 'record.json'), 'w') as fh:
        json.dump(clean(rec), fh, indent=1, allow_nan=False)
