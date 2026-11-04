"""rptfile.py - the parts of a SWMM 5 or OpenSWMM 6 report (.rpt) file a run record needs.

Read from the report: the engine banner, the ERROR and WARNING lines, the continuity tables (every row, with the
continuity error), the routing time-step summary, and the analysis options. Peaks and time series come from the
.out file, not from the report's summary tables: the binary file holds what the engine computed, and the report
tables are a second rendering of it (one OpenSWMM 6 alpha printed the routing step's maximum depth in the Node
Depth Summary, for example).

Written by Claude (Anthropic) for Robert Dickinson; see AI-USE.md.
"""
import re

_NUM = r'([-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?|nan|-?inf)'
_ERR = re.compile(r'^\s*ERROR\s+(\d+):?\s*(.*)$')
_WARN = re.compile(r'^\s*WARNING\s+(\d+):?\s*(.*)$')
_DOTS = re.compile(r'^\s*(.+?)\s*\.{2,}\s*(.*)$')
_COLON = re.compile(r'^\s*(.+?)\s*:\s+(.*)$')
CLOCK_LINES = ('Analysis begun on', 'Analysis ended on', 'Total elapsed time')


def _key(label):
    return re.sub(r'[^a-z0-9]+', '_', label.lower().replace('%', 'percent')).strip('_')


def _num(s):
    try:
        return float(s)
    except ValueError:
        return None


def parse(path, max_messages=200):
    """Return a dict: banner, errors, warnings (code, text, count), continuity, time_steps, options, clock."""
    with open(path, 'r', encoding='latin-1') as fh:
        lines = fh.read().splitlines()
    out = dict(banner=None, errors=[], warnings=[], warning_counts={}, continuity={}, time_steps={}, options={},
               clock={}, lines=len(lines))
    for ln in lines[:5]:
        s = ln.strip()
        if s and not s.startswith('-'):
            out['banner'] = s
            break
    i = 0
    n = len(lines)
    while i < n:
        ln = lines[i]
        m = _ERR.match(ln)
        if m:
            if len(out['errors']) < max_messages:
                out['errors'].append(dict(code=int(m.group(1)), text=m.group(2).strip()))
            i += 1
            continue
        m = _WARN.match(ln)
        if m:
            code = int(m.group(1))
            out['warning_counts'][str(code)] = out['warning_counts'].get(str(code), 0) + 1
            if len(out['warnings']) < max_messages:
                out['warnings'].append(dict(code=code, text=m.group(2).strip()))
            i += 1
            continue
        s = ln.strip()
        for c in CLOCK_LINES:
            if s.startswith(c):
                out['clock'][_key(c)] = s.split(':', 1)[1].strip() if ':' in s else s
        # a starred section title: ****, Title [units...], ****
        if s.startswith('****') and i + 2 < n and lines[i + 2].strip().startswith('****'):
            title_line = lines[i + 1]
            title = re.split(r'\s{2,}', title_line.strip())[0]
            units = re.split(r'\s{2,}', title_line.strip())[1:]
            j = i + 3
            if title == 'Analysis Options':
                while j < n and lines[j].strip():
                    m = _DOTS.match(lines[j])
                    if m:
                        out['options'][_key(m.group(1))] = m.group(2).strip()
                    j += 1
            elif title.endswith('Continuity'):
                rows = {}
                err = None
                while j < n and lines[j].strip():
                    m = _DOTS.match(lines[j])
                    if m:
                        vals = [_num(v) for v in m.group(2).split()]
                        label = m.group(1)
                        if label.startswith('Continuity Error'):
                            err = vals if len(vals) > 1 else (vals[0] if vals else None)
                        else:
                            rows[_key(label)] = vals if len(vals) > 1 else (vals[0] if vals else None)
                    elif lines[j].strip().startswith('---'):
                        pass
                    else:
                        # the quality tables name their pollutants in a header row
                        hdr = lines[j].split()
                        if hdr and not rows:
                            units = hdr
                    j += 1
                out['continuity'][_key(title)] = dict(units=units, rows=rows, error_percent=err)
            elif title == 'Routing Time Step Summary':
                hist = []
                while j < n and lines[j].strip():
                    m = _COLON.match(lines[j])
                    if m:
                        v = m.group(2).split()
                        label = m.group(1).strip()
                        if label[:1].isdigit():         # the step-size histogram: "5.000 - 3.155 sec : 100.00 %"
                            hist.append(dict(range=label, percent=_num(v[0]) if v else None))
                        else:
                            out['time_steps'][_key(label)] = _num(v[0]) if v else None
                    j += 1
                if hist:
                    out['time_steps']['histogram'] = hist
            i = j
            continue
        i += 1
    return out


def strip_clock(text):
    """The report with its three clock lines removed, as the byte gates compare it."""
    return '\n'.join(l for l in text.split('\n') if not l.strip().startswith(CLOCK_LINES))
