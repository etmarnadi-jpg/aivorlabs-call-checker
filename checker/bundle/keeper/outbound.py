from __future__ import annotations
import json
import os
import time
from pathlib import Path
from . import refuse, timefmt
PATH: Path | None = None
MAX_BYTES = 2000000
KEEP = 48 * 3600
HIS_KEYS = ('livekit-',)
SENTRY = 'sentry'

def use(state: Path) -> None:
    global PATH
    PATH = Path(state) / 'outbound.jsonl'

def log(m: str, to: str, now: float | None=None) -> None:
    if PATH is None:
        return
    row = {'at': round(now if now is not None else time.time(), 1), 'm': m, 'to': str(to)[:80]}
    try:
        PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(PATH, 'a') as f:
            f.write(json.dumps(row) + '\n')
        if PATH.stat().st_size > MAX_BYTES:
            _prune(row['at'])
    except OSError:
        pass

def _prune(now: float) -> None:
    keep = [r for r in rows(PATH) if now - r['at'] <= KEEP]
    tmp = PATH.with_suffix('.tmp')
    tmp.write_text(''.join((json.dumps(r) + '\n' for r in keep)))
    os.replace(tmp, PATH)

def rows(path: Path) -> list:
    out = []
    try:
        for line in Path(path).read_text().splitlines():
            try:
                out.append(json.loads(line))
            except ValueError:
                continue
    except OSError:
        pass
    return out

def his_key(r: dict) -> bool:
    to = r['to']
    if r['m'] == 'KEY':
        return any((Path(to).name.startswith(k) for k in HIS_KEYS))
    return r['m'] == 'RUN' and to.startswith('credit_probe') and ('livekit' in to.split()[1:])

def report(path: Path, now: float, hours: float=24) -> tuple:
    allr = rows(path)
    rs = [r for r in allr if now - r['at'] <= hours * 3600]
    if not rs:
        return (2, [f"Nothing is proven yet: the outbound log has no rows in the last {hours:g} hours ({('it is empty or missing' if not allr else 'its newest row is ' + timefmt.pacific(max((r['at'] for r in allr)), now))}), so the counts of Sentry calls that are not a GET, reads of account livekit's keys and commands on Luterson's line show nothing. A running watcher writes a row each minute."])
    sentry_writes = [r for r in rs if SENTRY in r['to'].lower() and r['m'] not in ('GET', 'KEY')]
    keys = [r for r in rs if his_key(r)]
    his_line = [r for r in rs if r['m'] == 'RUN' and refuse.refused(r['to'])]
    by = {}
    for r in rs:
        k = (r['m'], r['to'].split()[0] if r['m'] == 'RUN' else r['to'])
        by[k] = by.get(k, 0) + 1
    first = min((r['at'] for r in allr), default=None)
    lines = [f"Outbound, the last {hours:g} hours ({len(rs)} rows; the log starts {(timefmt.pacific(first, now) if first else 'nowhere: nothing logged yet')}):", f'- Sentry calls that are not a GET: {len(sentry_writes)}', f"- Reads of account livekit's keys (Luterson's project): {len(keys)}", f"- Commands on Luterson's line: {len(his_line)}"]
    lines += [f'- {m} {to}: {n}' for (m, to), n in sorted(by.items())]
    return (0 if not (sentry_writes or keys or his_line) else 1, lines)
