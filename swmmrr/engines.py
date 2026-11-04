"""engines.py - the engine registry (engines.json): resolve an engine's command, check that it is present, and
fingerprint the build a record was made with (SHA-256 of each artifact, and the commit of its working tree).

Written by Claude (Anthropic) for Robert Dickinson; see AI-USE.md.
"""
import hashlib
import json
import os
import re
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
REGISTRY = os.environ.get('SWMMRR_ENGINES', os.path.join(HERE, 'engines.json'))


def load(path=None):
    with open(path or REGISTRY) as fh:
        return json.load(fh)


def resolve(s, roots):
    return re.sub(r'\{([A-Z0-9_]+)\}', lambda m: os.environ.get(m.group(1), roots.get(m.group(1), m.group(0))), s)


def get(engine_id, reg=None):
    reg = reg or load()
    for e in reg['engines']:
        if e['id'] == engine_id:
            return e, reg
    raise KeyError('no engine %r in the registry (known: %s)' % (engine_id, ', '.join(x['id'] for x in reg['engines'])))


def command(e, reg):
    if not e.get('command'):
        return None
    return [resolve(c, reg['roots']) for c in e['command']]


def available(e, reg):
    """None when the engine can run here, else the reason it cannot."""
    if not e['capabilities'].get('simulate', True) or not e.get('command'):
        return e['capabilities'].get('reason', 'this engine does not run simulations')
    for a in e.get('artifacts', []):
        p = resolve(a, reg['roots'])
        if not os.path.exists(p):
            return 'missing build artifact ' + p
    return None


def _tree_hash(path):
    """SHA-256 of a file, or of a folder as the sorted list of (relative path, file SHA-256) pairs, skipping caches."""
    if os.path.isfile(path):
        h = hashlib.sha256()
        with open(path, 'rb') as fh:
            for b in iter(lambda: fh.read(1 << 20), b''):
                h.update(b)
        return h.hexdigest(), 1
    items = []
    for dp, dns, fns in os.walk(path):
        dns[:] = sorted(d for d in dns if d not in ('__pycache__', '.git', 'node_modules'))
        for f in sorted(fns):
            if f.endswith(('.pyc', '.log')):
                continue
            fp = os.path.join(dp, f)
            items.append(os.path.relpath(fp, path) + '\0' + _tree_hash(fp)[0])
    return hashlib.sha256('\n'.join(items).encode()).hexdigest(), len(items)


def _git(d):
    if not d or not os.path.isdir(d):
        return None
    try:
        head = subprocess.run(['git', '-C', d, 'rev-parse', 'HEAD'], capture_output=True, text=True, timeout=20).stdout.strip()
        dirty = subprocess.run(['git', '-C', d, 'status', '--porcelain', '--untracked-files=no'],
                               capture_output=True, text=True, timeout=60).stdout.strip() != ''
        return dict(commit=head or None, dirty=dirty) if head else None
    except (OSError, subprocess.SubprocessError):
        return None


def fingerprint(e, reg):
    """What exactly will run: each artifact's SHA-256 (a folder's as a tree hash), one combined build SHA-256, and
    the working tree's commit (with a dirty flag: uncommitted changes there may or may not touch this engine)."""
    arts = []
    for a in e.get('artifacts', []):
        p = resolve(a, reg['roots'])
        h, n = _tree_hash(os.path.realpath(p))
        arts.append(dict(path=p, sha256=h, files=n))
    build = hashlib.sha256('\n'.join(a['sha256'] for a in arts).encode()).hexdigest() if arts else None
    return dict(build_sha256=build, artifacts=arts, git=_git(resolve(e['git'], reg['roots']) if e.get('git') else None))
