from __future__ import annotations
import json
import re
from pathlib import Path
from . import refuse

def emergency_res(words) -> list:
    out = []
    for w in words or []:
        parts = [re.escape(p.strip()) for p in str(w).split('...') if p.strip()]
        if parts:
            out.append(re.compile('(?i)\\b' + '\\b[^.?!]*\\b'.join(parts) + '\\b'))
    return out

def discover(watch) -> dict:
    lines = {}
    for root in watch.roots:
        for f in sorted(Path(root).glob('*/line.json')):
            if refuse.refused(f.parent.name):
                continue
            try:
                d = json.loads(f.read_text())
            except (OSError, ValueError):
                continue
            if not isinstance(d, dict) or refuse.refused(d.get('id'), d.get('business'), d.get('agent'), d.get('number'), d.get('ownerPhone')):
                continue
            em = d.get('emergency') or {}
            if str(d.get('id') or f.parent.name) in lines:
                continue
            lines[str(d.get('id') or f.parent.name)] = {'id': str(d.get('id') or f.parent.name), 'business': str(d.get('business') or ''), 'test': d.get('test') is True, 'owner': str(d.get('owner') or ''), 'ownerPronoun': str(d.get('ownerPronoun') or ''), 'emergency': [p.pattern for p in emergency_res(em.get('words'))], 'never': [str(x).lower() for x in em.get('never') or []], 'file': str(f)}
    return lines
TEMPLATES = (('trees', 'cedar', re.compile('(?i)\\btrees?\\b')), ('moving', 'harbor', re.compile('(?i)\\bmov(?:ing|ers?)\\b|\\bhaul(?:ing|ers?)\\b')), ('general', 'quarry', re.compile('.')))

def template_for(business, lines: dict) -> dict | None:
    b = str(business or '').strip()
    if not b or refuse.refused(b):
        return None
    for trade, tid, rx in TEMPLATES:
        if rx.search(b):
            t = lines.get(tid)
            if not t:
                return None
            return dict(t, owner='', ownerPronoun='', business=b, fromTemplate=tid, trade=trade)
    return None
