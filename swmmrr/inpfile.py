"""inpfile.py - what a run record says about the model: its hash, its main options, its element counts, and the
other files it reads (rainfall, time series, climate, hot start and interface files), each with its own hash, so a
record names everything that went into the run.

Written by Claude (Anthropic) for Robert Dickinson; see AI-USE.md.
"""
import hashlib
import os
import shlex

OPTION_KEYS = ('FLOW_UNITS', 'FLOW_ROUTING', 'INFILTRATION', 'START_DATE', 'START_TIME', 'REPORT_START_DATE',
               'REPORT_START_TIME', 'END_DATE', 'END_TIME', 'REPORT_STEP', 'ROUTING_STEP', 'SURCHARGE_METHOD',
               'ALLOW_PONDING', 'IGNORE_RAINFALL', 'IGNORE_SNOWMELT', 'IGNORE_GROUNDWATER', 'IGNORE_RDII',
               'IGNORE_ROUTING', 'IGNORE_QUALITY', 'THREADS')
COUNT_SECTIONS = ('RAINGAGES', 'SUBCATCHMENTS', 'JUNCTIONS', 'OUTFALLS', 'DIVIDERS', 'STORAGE', 'CONDUITS', 'PUMPS',
                  'ORIFICES', 'WEIRS', 'OUTLETS', 'POLLUTANTS', 'LID_CONTROLS', 'LID_USAGE', 'CONTROLS', 'AQUIFERS')


def sha256_file(path, chunk=1 << 20):
    h = hashlib.sha256()
    with open(path, 'rb') as fh:
        while True:
            b = fh.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def _split(line):
    try:
        return shlex.split(line, posix=True)
    except ValueError:
        return line.split()


def read(path):
    """Model identity: path, size, SHA-256, options, element counts and the files the model reads or writes."""
    folder = os.path.dirname(os.path.abspath(path))
    with open(path, 'r', encoding='latin-1') as fh:
        text = fh.read()
    sections = {}
    section = None
    for raw in text.splitlines():
        line = raw.split(';', 1)[0].strip() if not raw.lstrip().startswith(';') else ''
        if not line:
            continue
        if line.startswith('[') and ']' in line:
            section = line[1:line.index(']')].upper()
            sections.setdefault(section, [])
            continue
        if section:
            sections[section].append(line)
    options = {}
    for line in sections.get('OPTIONS', []):
        t = line.split(None, 1)
        if len(t) == 2 and t[0].upper() in OPTION_KEYS:
            options[t[0].upper()] = t[1].strip()
    counts = {}
    for s in COUNT_SECTIONS:
        if s in sections:
            if s == 'CONTROLS':
                counts['control_rules'] = sum(1 for l in sections[s] if l.upper().startswith('RULE'))
            else:
                counts[s.lower()] = len(sections[s])
    refs = []

    def add(kind, name):
        p = name if os.path.isabs(name) else os.path.join(folder, name)
        ent = dict(kind=kind, name=name, exists=os.path.isfile(p))
        if ent['exists']:
            ent['sha256'] = sha256_file(p)
            ent['bytes'] = os.path.getsize(p)
        refs.append(ent)

    for line in sections.get('FILES', []):
        t = _split(line)
        if len(t) >= 3:
            if t[0].upper() == 'USE':
                add('use ' + t[1].lower(), t[2])
            else:
                refs.append(dict(kind='save ' + t[1].lower(), name=t[2], exists=None))   # written by the run
    for sec in ('RAINGAGES', 'TIMESERIES', 'TEMPERATURE', 'EVAPORATION', 'ADJUSTMENTS'):
        for line in sections.get(sec, []):
            t = _split(line)
            up = [x.upper() for x in t]
            if 'FILE' in up:
                k = up.index('FILE')
                if k + 1 < len(t):
                    add(sec.lower() + ' file', t[k + 1])
    for line in sections.get('LID_USAGE', []):
        t = _split(line)
        if len(t) >= 9 and t[8] not in ('*', '0'):
            refs.append(dict(kind='lid report (written)', name=t[8], exists=None))
    return dict(path=os.path.abspath(path), name=os.path.basename(path), bytes=os.path.getsize(path),
                sha256=sha256_file(path), options=options, counts=counts, files=refs)
