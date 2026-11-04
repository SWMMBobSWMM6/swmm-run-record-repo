"""compare.py - compare two run records (schema swmm-run-diff/1).

The comparison works down from the strongest statement to the weakest:
  IDENTICAL_FILES     the .out files are byte-identical and the reports are, apart from their three clock lines;
  IDENTICAL_RESULTS   the .out results blocks are byte-identical (the headers differ: a version number, say);
  WITHIN_TOLERANCE    every value of every variable of every object both files share, at every report time both
                      share, satisfies |a - b| <= abs + rel * max(|a|, |b|) for the chosen profile;
  DIFFERENT           at least one value does not;
  SAME_ERRORS / DIFFERENT_ERRORS   both runs stopped on ERROR lines: are the codes the same?
  NOT_COMPARABLE      different models, or one run completed and the other did not, or no report time in common.
The numbers behind the verdict are always given (worst difference per variable, where and when), because a
verdict is only as good as its tolerance. Two records from different families (EPA SWMM 5.2.4 and OpenSWMM 6)
can be compared the same way, but OpenSWMM 6 is a new engine, not a translation of 5.2.4, so differences there are
findings to explain, not defects by definition.

Written by Claude (Anthropic) for Robert Dickinson; see AI-USE.md.
"""
import datetime as dt
import json
import math

from . import outfile, record

SCHEMA = 'swmm-run-diff/1'
PROFILES = {'strict': dict(abs=0.0, rel=0.0), 'roundoff': dict(abs=1e-6, rel=1e-6),
            'engineering': dict(abs=1e-3, rel=1e-2)}


def load(path):
    with open(path) as fh:
        return json.load(fh)


def _side(r):
    f = r.get('files', {})
    return dict(engine=r['engine']['id'], family=r['engine']['family'],
                build_sha256=(r['engine'].get('fingerprint') or {}).get('build_sha256'),
                model=r['model']['name'], model_sha256=r['model']['sha256'], status=r['run']['status'],
                out_sha256=f.get('out', {}).get('sha256'), results_sha256=f.get('out', {}).get('results_sha256'),
                rpt_sha256_without_clock=f.get('rpt', {}).get('sha256_without_clock'))


def compare(ra, rb, profile='engineering'):
    tol = PROFILES[profile]
    d = dict(schema=SCHEMA, created=dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds'), tool=record.TOOL,
             a=_side(ra), b=_side(rb), profile=dict(name=profile, **tol),
             same_family=ra['engine']['family'] == rb['engine']['family'])
    d['same_model'] = d['a']['model_sha256'] == d['b']['model_sha256']
    d['continuity'] = {}
    for sec in sorted(set(ra.get('continuity', {})) | set(rb.get('continuity', {}))):
        ea = ra.get('continuity', {}).get(sec, {}).get('error_percent')
        eb = rb.get('continuity', {}).get(sec, {}).get('error_percent')
        d['continuity'][sec] = dict(a=ea, b=eb)
    keys = ('minimum_time_step', 'average_time_step', 'average_iterations_per_step', 'percent_of_steps_not_converging')
    d['time_steps'] = {k: dict(a=ra.get('time_steps', {}).get(k), b=rb.get('time_steps', {}).get(k)) for k in keys
                       if k in ra.get('time_steps', {}) or k in rb.get('time_steps', {})}
    d['run'] = dict(a=dict(status=ra['run']['status'], wall_seconds=ra['run'].get('wall_seconds')),
                    b=dict(status=rb['run']['status'], wall_seconds=rb['run'].get('wall_seconds')))
    if not d['same_model']:
        d['verdict'] = 'NOT_COMPARABLE'
        d['reason'] = 'different models (input files differ)'
        return d
    sa, sb = ra['run']['status'], rb['run']['status']
    if sa == 'error' and sb == 'error':
        ca = sorted(e['code'] for e in ra['run']['errors'])
        cb = sorted(e['code'] for e in rb['run']['errors'])
        d['errors'] = dict(a=ca, b=cb)
        d['verdict'] = 'SAME_ERRORS' if ca == cb else 'DIFFERENT_ERRORS'
        return d
    if sa != 'completed' or sb != 'completed':
        d['verdict'] = 'NOT_COMPARABLE'
        d['reason'] = 'run A %s, run B %s' % (sa, sb)
        return d
    if d['a']['out_sha256'] == d['b']['out_sha256'] and \
            d['a']['rpt_sha256_without_clock'] == d['b']['rpt_sha256_without_clock']:
        d['verdict'] = 'IDENTICAL_FILES'
        return d
    oa = outfile.OutFile(ra['files']['out']['path'])
    ob = outfile.OutFile(rb['files']['out']['path'])
    if d['a']['results_sha256'] == d['b']['results_sha256'] and oa.nperiods == ob.nperiods:
        d['verdict'] = 'IDENTICAL_RESULTS'
        d['note'] = ('the .out results blocks are byte-identical; ' +
                     ('the reports differ beyond their clock lines' if d['a']['rpt_sha256_without_clock'] != d['b']['rpt_sha256_without_clock']
                      else 'the .out headers differ'))
        return d
    d.update(_values(oa, ob, tol))
    return d


def _values(oa, ob, tol):
    """Compare every value the two files share, by object name, variable name and report time."""
    da, db = oa.dates(), ob.dates()
    ka = {round(x * 86400.0): k for k, x in enumerate(da)}
    pairs = [(ka[round(x * 86400.0)], k) for k, x in enumerate(db) if round(x * 86400.0) in ka]
    grid = dict(a_periods=oa.nperiods, b_periods=ob.nperiods, common_periods=len(pairs),
                same_grid=oa.nperiods == ob.nperiods == len(pairs))
    lists = (('sub', 'subcatchments', 'subcatchments'), ('node', 'nodes', 'nodes'), ('link', 'links', 'links'))
    idx = []                     # (offset in A's period, offset in B's period, kind, object, variable)
    missing = {}
    base_a = base_b = 0
    for kind, attr, label in lists:
        na, nb = getattr(oa, attr), getattr(ob, attr)
        va, vb = oa.var_names(kind), ob.var_names(kind)
        nva, nvb = len(va), len(vb)
        pos_b = {n: j for j, n in enumerate(nb)}
        vpos_b = {n: q for q, n in enumerate(vb)}
        missing[label] = dict(only_in_a=sorted(set(na) - set(nb))[:50], only_in_b=sorted(set(nb) - set(na))[:50])
        for j, name in enumerate(na):
            if name not in pos_b:
                continue
            for q, v in enumerate(va):
                if v in vpos_b:
                    idx.append((base_a + j * nva + q, base_b + pos_b[name] * nvb + vpos_b[v], kind, name, v))
        base_a += len(na) * nva
        base_b += len(nb) * nvb
    va, vb = oa.var_names('sys'), ob.var_names('sys')
    for q, v in enumerate(va):
        if v in vb:
            idx.append((base_a + q, base_b + vb.index(v), 'sys', None, v))
    stats = {}
    for ia, ib, kind, name, v in idx:
        stats.setdefault((kind, v), dict(compared=0, outside=0, max_abs_diff=0.0, max_rel_diff=0.0, worst=None,
                                         worst_score=-1.0))
    ab, rl = tol['abs'], tol['rel']
    for pa, pb in pairs:
        xa = oa.period_values(pa)
        xb = ob.period_values(pb)
        for ia, ib, kind, name, v in idx:
            a, b = xa[ia], xb[ib]
            s = stats[(kind, v)]
            s['compared'] += 1
            if a == b:
                continue
            if math.isnan(a) or math.isnan(b):
                diff, m = float('inf'), float('inf')
            else:
                diff, m = abs(a - b), max(abs(a), abs(b))
            rel = diff / m if m > 0 else 0.0
            if diff > ab + rl * m:
                s['outside'] += 1
            if diff > s['max_abs_diff']:
                s['max_abs_diff'] = diff
            if rel > s['max_rel_diff']:
                s['max_rel_diff'] = rel
            score = diff / (ab + rl * m) if ab + rl * m > 0 else diff
            if score > s['worst_score']:
                s['worst_score'] = score
                s['worst'] = dict(id=name, time=record.swmm_date(da[pa]), a=a, b=b)
    variables = []
    for (kind, v), s in stats.items():
        s['tolerance_ratio'] = max(s.pop('worst_score'), 0.0)   # worst |a - b| / (abs + rel * max(|a|, |b|)); over 1 is outside
        variables.append(dict(kind=kind, variable=v, **s))
    variables.sort(key=lambda x: (-x['outside'], -x['tolerance_ratio']))
    outside = sum(x['outside'] for x in variables)
    compared = sum(x['compared'] for x in variables)
    verdict = 'NOT_COMPARABLE' if not pairs else ('WITHIN_TOLERANCE' if outside == 0 else 'DIFFERENT')
    return dict(verdict=verdict, grid=grid, objects_missing=missing, values_compared=compared, values_outside=outside,
                max_tolerance_ratio=max((x['tolerance_ratio'] for x in variables), default=0.0), variables=variables)
