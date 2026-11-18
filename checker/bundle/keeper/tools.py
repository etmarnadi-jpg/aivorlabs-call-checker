from __future__ import annotations
import json
import os
import re
import shutil
import statistics
import subprocess
import time
from pathlib import Path
from . import outbound
CHECK_LINE = re.compile('^(OK  |FAIL) (.+?)(?::\\s(.*))?$')

def elijah_check(cfg, events: Path, no_booking: bool) -> dict:
    cmd = [str(cfg.check_py), '-I', str(cfg.elijah_check), str(events)] + (['--no-booking'] if no_booking else [])
    outbound.log('RUN', 'elijah_check')
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired) as e:
        return {'error': type(e).__name__}
    checks = []
    for line in r.stdout.splitlines():
        m = CHECK_LINE.match(line)
        if m:
            checks.append((m.group(1) == 'OK  ', m.group(2).strip()))
    verdict = next((l.strip() for l in r.stdout.splitlines() if l.strip() in ('PASS', 'FAIL')), None)
    if r.returncode or not checks or verdict is None:
        last = (r.stderr.strip().splitlines() or ['no output'])[-1]
        return {'error': re.sub('[^A-Za-z ]', ' ', last.split(':')[0])[:60].strip() or 'no output'}
    return {'checks': checks, 'pass': verdict == 'PASS'}

def _seed(src: Path, dst: Path, wav: Path) -> None:
    if src.exists() and (not dst.exists()) and (src.stat().st_mtime >= wav.stat().st_mtime):
        shutil.copyfile(src, dst)
        os.chmod(dst, 384)

def speed(cfg, call, until: float | None=None) -> dict:
    if not call.wav.exists():
        return {'error': 'no recording'}
    work = Path(cfg.state) / 'grade' / call.label
    gdir = work / 'grade'
    gdir.mkdir(parents=True, exist_ok=True)
    for p in (Path(cfg.state) / 'grade', work, gdir):
        os.chmod(p, 448)
    link = work / (call.label + '.wav')
    if not link.is_symlink():
        link.symlink_to(call.wav.resolve())
    for side in ('caller', 'recep'):
        _seed(call.dir / 'grade' / f'{call.stem}.{side}.json', gdir / f'{call.label}.{side}.json', call.wav)
    out = work / 'speed.json'
    fresh = lambda: out.exists() and out.stat().st_mtime >= call.wav.stat().st_mtime
    ran = not all(((gdir / f'{call.label}.{s}.json').exists() for s in ('caller', 'recep')))
    cmd = [str(cfg.grade_py), str(cfg.callgrade), str(link), '--json', str(out)]
    if getattr(cfg, 'speed_async', False) and ((work / 'speed.run').exists() or not fresh()):
        st = _background(cmd, work, fresh, ran)
        if 'done' not in st:
            return st
        ran = st['ran']
    elif not fresh():
        outbound.log('RUN', 'callgrade')
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=SPEED_MAX, cwd=str(work))
        except (OSError, subprocess.TimeoutExpired) as e:
            return {'error': type(e).__name__}
        if r.returncode or not out.exists():
            return {'error': _last(r.stderr), 'ran': ran}
    else:
        ran = False
    try:
        d = json.loads(out.read_text())
    except (OSError, ValueError):
        return {'error': 'unreadable'}
    rows = [r for r in d.get('rows') or [] if until is None or (r.get('t') or 0) < until]
    return dict(summarize(rows, len(d.get('recep') or [])), **{'ran': True} if ran else {})
SPEED_MAX = 300
RUNNING = {}

def _last(stderr: str) -> str:
    last = (stderr.strip().splitlines() or ['no output'])[-1]
    return re.sub('[^A-Za-z ]', ' ', last.split(':')[0])[:60].strip() or 'no output'

def _alive(pid) -> bool:
    try:
        os.kill(int(pid), 0)
        return True
    except (OSError, ValueError, TypeError):
        return False

def _background(cmd: list, work: Path, fresh, ran: bool) -> dict:
    mark, err = (work / 'speed.run', work / 'speed.err')
    m = None
    try:
        m = json.loads(mark.read_text())
    except (OSError, ValueError):
        pass
    if m:
        p = RUNNING.get(str(work))
        going = p.poll() is None if p is not None else _alive(m.get('pid'))
        if going and time.time() - float(m.get('at') or 0) <= SPEED_MAX:
            return {'running': True}
        if going:
            try:
                os.kill(int(m['pid']), 9)
            except (OSError, ValueError, KeyError):
                pass
        if p is not None:
            p.wait()
        RUNNING.pop(str(work), None)
        mark.unlink(missing_ok=True)
        was = bool(m.get('ran'))
        if going:
            return {'error': 'TimeoutExpired', 'ran': was}
        if fresh():
            return {'done': True, 'ran': was}
        text = err.read_text(errors='replace') if err.exists() else ''
        return {'error': _last(text), 'ran': was}
    for other in work.parent.glob('*/speed.run'):
        try:
            o = json.loads(other.read_text())
        except (OSError, ValueError):
            continue
        if _alive(o.get('pid')) and time.time() - float(o.get('at') or 0) <= SPEED_MAX:
            q = RUNNING.get(str(other.parent))
            if q is None or q.poll() is None:
                return {'running': True, 'waiting': True}
    outbound.log('RUN', 'callgrade')
    try:
        with open(err, 'w') as ef:
            p = subprocess.Popen(cmd, cwd=str(work), stdout=subprocess.DEVNULL, stderr=ef, stdin=subprocess.DEVNULL)
    except OSError as e:
        return {'error': type(e).__name__}
    RUNNING[str(work)] = p
    mark.write_text(json.dumps({'pid': p.pid, 'at': time.time(), 'ran': ran}))
    os.chmod(mark, 384)
    return {'running': True}

def background_done(state: Path) -> bool:
    for mark in (Path(state) / 'grade').glob('*/speed.run'):
        p = RUNNING.get(str(mark.parent))
        if p is not None:
            if p.poll() is not None:
                return True
            continue
        try:
            m = json.loads(mark.read_text())
        except (OSError, ValueError):
            continue
        if not _alive(m.get('pid')):
            if time.time() - float(m.get('at') or 0) > 2 * SPEED_MAX:
                mark.unlink(missing_ok=True)
                continue
            return True
    return False

def late(r) -> float:
    return r['real'] if r.get('real') is not None else r['word']

def summarize(rows: list, recep_parts: int=0) -> dict:
    vals = [(late(r), r.get('t')) for r in rows if r.get('word') is not None]
    if not vals:
        return {'n': 0, 'recepParts': recep_parts}
    worst = max(vals)
    return {'n': len(vals), 'worst': round(worst[0], 2), 'worstAt': worst[1], 'typical': round(statistics.median((v for v, _ in vals)), 2), 'over': sum((v > 0.5 for v, _ in vals)), 'overCap': sum((v > 1.5 for v, _ in vals)), 'late': [v for v, _ in vals], 'recepParts': recep_parts}
