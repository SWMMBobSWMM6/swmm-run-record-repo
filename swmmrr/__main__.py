"""python3 -m swmmrr COMMAND ...

  engines                                  list the registry: which engines can run here, and why not
  run ENGINE MODEL.inp -d DIR [--series KIND:ID:VAR ...] [--timeout S]
                                           run one engine, keep run.rpt, run.out and record.json in DIR
  compare A/record.json B/record.json [--profile engineering|roundoff|strict] [-o diff.json]
  matrix MODEL.inp -d DIR [--engines ID,ID,...] [--timeout S] [--reuse] [--profile P]
                                           run every engine (or the ones named), compare each with its family's
                                           reference and the two references with each other, and write
                                           DIR/matrix.json and DIR/matrix.md

Written by Claude (Anthropic) for Robert Dickinson; see AI-USE.md.
"""
import argparse
import json
import os
import sys

from . import compare, engines, record


def _fmt(x, nd=3):
    if x is None:
        return '-'
    if isinstance(x, float):
        return ('%.' + str(nd) + 'g') % x
    return str(x)


def cmd_engines(a):
    reg = engines.load()
    for e in reg['engines']:
        why = engines.available(e, reg)
        print('%-18s %-8s %-11s %-12s %s' % (e['id'], e['family'], e['language'], e['role'], 'ready' if not why else 'not available: ' + why))


def cmd_run(a):
    r = record.run(a.engine, a.model, a.dir, timeout=a.timeout, series=a.series)
    print('%s: %s in %.2f s; record %s' % (a.engine, r['run']['status'], r['run'].get('wall_seconds') or 0,
                                           os.path.join(a.dir, 'record.json')))


def cmd_compare(a):
    d = compare.compare(compare.load(a.a), compare.load(a.b), a.profile)
    if a.o:
        with open(a.o, 'w') as fh:
            json.dump(record.clean(d), fh, indent=1, allow_nan=False)
    print(d['verdict'], d.get('reason', '') or d.get('note', ''))
    for v in d.get('variables', [])[:12]:
        w = v['worst'] or {}
        print('  %-5s %-20s outside %6d of %8d  worst x%-8s at %s %s (%s vs %s)' % (
            v['kind'], v['variable'], v['outside'], v['compared'], _fmt(v['tolerance_ratio']), w.get('id'), w.get('time'),
            _fmt(w.get('a'), 6), _fmt(w.get('b'), 6)))


def cmd_matrix(a):
    reg = engines.load()
    ids = a.engines.split(',') if a.engines else [e['id'] for e in reg['engines']]
    os.makedirs(a.dir, exist_ok=True)
    recs = {}
    for eid in ids:
        wd = os.path.join(a.dir, eid)
        rp = os.path.join(wd, 'record.json')
        if a.reuse and os.path.exists(rp):
            recs[eid] = compare.load(rp)
            if recs[eid]['model']['sha256'] == record.inpfile.read(a.model)['sha256']:
                print('%-18s reused' % eid, flush=True)
                continue
        recs[eid] = record.run(eid, a.model, wd, timeout=a.timeout)
        print('%-18s %s %s s' % (eid, recs[eid]['run']['status'], recs[eid]['run'].get('wall_seconds', '-')), flush=True)
    refs = {f: reg['families'][f]['reference'] for f in reg['families']}
    rows = []
    for eid in ids:
        r = recs[eid]
        fam = r['engine']['family']
        ref = refs.get(fam)
        row = dict(engine=eid, family=fam, language=r['engine']['language'], role=r['engine']['role'],
                   status=r['run']['status'], exit_code=r['run'].get('exit_code'),
                   exit_code_agrees_with_report=r['run'].get('exit_code_agrees_with_report'),
                   wall_seconds=r['run'].get('wall_seconds'), cpu_seconds=r['run'].get('cpu_seconds'),
                   build_sha256=(r['engine'].get('fingerprint') or {}).get('build_sha256'),
                   results_sha256=r.get('files', {}).get('out', {}).get('results_sha256'),
                   continuity={k: v.get('error_percent') for k, v in r.get('continuity', {}).items()},
                   reason=r['run'].get('reason'))
        if ref and ref != eid and ref in recs and r['run']['status'] != 'not_run':
            d = compare.compare(recs[ref], r, a.profile)
            row['vs_reference'] = dict(reference=ref, verdict=d['verdict'], values_outside=d.get('values_outside'),
                                       max_tolerance_ratio=d.get('max_tolerance_ratio'))
        rows.append(row)
    cross = None
    if all(x in recs for x in refs.values()):
        fams = list(refs)
        d = compare.compare(recs[refs[fams[0]]], recs[refs[fams[1]]], a.profile)
        with open(os.path.join(a.dir, 'cross_family_diff.json'), 'w') as fh:
            json.dump(record.clean(d), fh, indent=1, allow_nan=False)
        cross = dict(a=refs[fams[0]], b=refs[fams[1]], verdict=d['verdict'], values_compared=d.get('values_compared'),
                     values_outside=d.get('values_outside'), max_tolerance_ratio=d.get('max_tolerance_ratio'),
                     worst=[dict(kind=v['kind'], variable=v['variable'], outside=v['outside'], compared=v['compared'],
                                 tolerance_ratio=v['tolerance_ratio'], worst=v['worst']) for v in d.get('variables', [])[:8]],
                     continuity=d['continuity'])
    m0 = next(iter(recs.values()))['model']
    M = dict(schema='swmm-run-matrix/1', tool=record.TOOL, model=dict(name=m0['name'], sha256=m0['sha256'],
             options=m0['options'], counts=m0['counts']), profile=dict(name=a.profile, **compare.PROFILES[a.profile]),
             engines=rows, cross_family=cross)
    with open(os.path.join(a.dir, 'matrix.json'), 'w') as fh:
        json.dump(record.clean(M), fh, indent=1, allow_nan=False)
    with open(os.path.join(a.dir, 'matrix.md'), 'w') as fh:
        fh.write(markdown(M))
    print(markdown(M))


def markdown(M):
    m = M['model']
    L = ['# %s' % m['name'], '',
         'Model SHA-256 `%s`; %s; routing %s, flow units %s. Tolerance profile `%s` (|a - b| <= %g + %g * max(|a|, |b|)).'
         % (m['sha256'][:16], ', '.join('%s %s' % (v, k) for k, v in m['counts'].items()), m['options'].get('FLOW_ROUTING', '-'),
            m['options'].get('FLOW_UNITS', '-'), M['profile']['name'], M['profile']['abs'], M['profile']['rel']), '',
         '| Engine | Status | Exit code | Wall s | Results block (SHA-256) | Against its family reference | Runoff cont. % | Routing cont. % |',
         '|---|---|---|---|---|---|---|---|']
    for r in M['engines']:
        vs = r.get('vs_reference')
        vtxt = 'reference' if r['role'] == 'reference' else (
            '%s%s' % (vs['verdict'], (' (%s values outside, worst x%s)' % (vs['values_outside'], _fmt(vs['max_tolerance_ratio'])))
                      if vs['verdict'] in ('DIFFERENT', 'WITHIN_TOLERANCE') else '') if vs else '-')
        ec = '-' if r['exit_code'] is None else ('%s%s' % (r['exit_code'], '' if r['exit_code_agrees_with_report'] in (True, None) else ' (disagrees with report)'))
        c = r['continuity']
        L.append('| %s | %s | %s | %s | %s | %s | %s | %s |' % (
            r['engine'], r['status'] if r['status'] != 'not_run' else 'not run: ' + (r['reason'] or ''), ec,
            _fmt(r['wall_seconds']), ('`%s`' % r['results_sha256'][:12]) if r['results_sha256'] else '-', vtxt,
            _fmt(c.get('runoff_quantity_continuity')), _fmt(c.get('flow_routing_continuity'))))
    x = M.get('cross_family')
    if x:
        L += ['', '## %s against %s' % (x['b'], x['a']), '',
              'Verdict %s: %s of %s values outside the tolerance, worst x%s. Continuity errors (%%): %s.' % (
                  x['verdict'], x['values_outside'], x['values_compared'], _fmt(x['max_tolerance_ratio']),
                  '; '.join('%s %s / %s' % (k.replace('_', ' '), _fmt(v['a']), _fmt(v['b'])) for k, v in x['continuity'].items())),
              '', '| Kind | Variable | Outside | Compared | Worst x tolerance | Where, when | A | B |', '|---|---|---|---|---|---|---|---|']
        for v in x['worst']:
            w = v['worst'] or {}
            L.append('| %s | %s | %s | %s | %s | %s %s | %s | %s |' % (v['kind'], v['variable'], v['outside'], v['compared'],
                     _fmt(v['tolerance_ratio']), w.get('id') or '', w.get('time') or '', _fmt(w.get('a'), 6), _fmt(w.get('b'), 6)))
    return '\n'.join(L) + '\n'


def main(argv=None):
    ap = argparse.ArgumentParser(prog='swmmrr', description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest='cmd', required=True)
    sp.add_parser('engines').set_defaults(f=cmd_engines)
    p = sp.add_parser('run')
    p.add_argument('engine'); p.add_argument('model'); p.add_argument('-d', '--dir', required=True)
    p.add_argument('--series', nargs='*'); p.add_argument('--timeout', type=float, default=3600.0)
    p.set_defaults(f=cmd_run)
    p = sp.add_parser('compare')
    p.add_argument('a'); p.add_argument('b'); p.add_argument('--profile', default='engineering', choices=compare.PROFILES)
    p.add_argument('-o'); p.set_defaults(f=cmd_compare)
    p = sp.add_parser('matrix')
    p.add_argument('model'); p.add_argument('-d', '--dir', required=True); p.add_argument('--engines')
    p.add_argument('--timeout', type=float, default=3600.0); p.add_argument('--reuse', action='store_true')
    p.add_argument('--profile', default='engineering', choices=compare.PROFILES)
    p.set_defaults(f=cmd_matrix)
    a = ap.parse_args(argv)
    a.f(a)


if __name__ == '__main__':
    sys.exit(main())
