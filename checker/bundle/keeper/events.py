from __future__ import annotations
import json
import os
from pathlib import Path

def read(path: Path) -> tuple:
    evs, good, bad, blank = ([], [], 0, 0)
    try:
        raw = Path(path).read_bytes().decode('utf-8', errors='replace')
    except OSError:
        return (None, [], 0, 0)
    for line in raw.splitlines():
        if not line.strip():
            blank += 1
            continue
        try:
            r = json.loads(line)
        except ValueError:
            bad += 1
            continue
        if not isinstance(r, dict):
            bad += 1
            continue
        e = r.get('ev')
        if isinstance(e, str) and (not e.strip()):
            blank += 1
            continue
        if isinstance(e, str):
            try:
                e = json.loads(e)
            except ValueError:
                bad += 1
                continue
        if not isinstance(e, dict):
            bad += 1
            continue
        e['_rt'] = r.get('rt') if isinstance(r.get('rt'), (int, float)) else 0.0
        evs.append(e)
        good.append(line)
    return (evs, good, bad, blank)

def clean_copy(state: Path, label: str, good: list) -> Path:
    d = Path(state) / 'clean'
    d.mkdir(parents=True, exist_ok=True)
    os.chmod(d, 448)
    p = d / f'{label}.events.jsonl'
    tmp = p.with_name(p.name + '.tmp')
    tmp.write_text(''.join((g + '\n' for g in good)))
    os.chmod(tmp, 384)
    os.replace(tmp, p)
    return p
