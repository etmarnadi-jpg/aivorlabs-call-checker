#!/usr/bin/env python3
"""E6, the call checker's GitHub copy (arch-job6, 17 Nov 2026; Q8 waits on Ethan): one run judges every finished call waiting at
rec-drop that it has not judged yet, the way the Mac's checker does (com.ethan.keeper-loop: keeper/tick.py, judge.judge, then
apply_skip and the three marks tick adds), with the Mac's own judging code copied into bundle/ by bundle.py.

Read-only, always: rec-drop is read with its READ key (GET /list and GET /f/<name> only; the Mac's rec-pull still takes and deletes
the files), nothing is written to Elijah's or Luterson's records, and Luterson's line is refused by name (keeper/refuse.py).

Where the calls come from:
  --source rec-drop   env REC_DROP_URL, REC_DROP_READ_KEY (read-only), REC_SEAL_KEY (unseals; AES-256-GCM as rec-pull)
  --source dir        --dir <folder>: a folder of call files (<stem>.wav, .json, .events.jsonl), for tests

What it leaves:
  <state>/seen.json             the calls already judged (labels only), carried from run to run (the workflow's cache)
  <state>/verdicts/<label>.json the verdict, the same fields as the Mac checker's state/verdicts/<label>.json
  --summary <file>              one row per call: label, robot, the promises' results, the card ids (no caller's words)
  stdout                        one plain line per call (label, PASS or the card ids), and a last count line
Sentry (only with env SENTRY_DSN set, a send-only key): one event per card id a non-robot call opened, project
receptionist-agent, environment "call-checker", fingerprint ["keeper-card", <card id>] (the Mac's cards-to-sentry issue for the
same card), tag from=github, digit runs of 7 or more blanked. Robot calls never send, as on the Mac.

A call still pending (its email may still be on its way: judge's mail_wait) is waited for inside the run, up to --wait seconds.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import shutil
import sys
import tempfile
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
BUNDLE = HERE / "bundle"
sys.path.insert(0, str(BUNDLE))
from keeper import calls as callmod, judge as judgemod, outbound, refuse, scrub   # noqa: E402 - the Mac's own code, copied

RECNAME = re.compile(r"^\d{8}-\d{6}Z-(.+)$")
PART = re.compile(r"\.part\d{3}$")
LEVEL = {"CODE": "error", "OUTSIDE": "warning", "WALL": "warning", "CHECK IS WRONG": "info"}
BACKFILL_HOURS = 6.0     # as the Mac's first run: a call that hung up longer ago than this is left alone (0 = judge all)


class Cfg:
    """The fields of the Mac's keeper Config that judge.py and tools.py read, nothing else."""

    def __init__(self, state: Path, grade_py: str):
        self.state = state
        self.check_py = sys.executable
        self.elijah_check = BUNDLE / "check" / "elijah_check.py"
        self.grade_py = grade_py
        self.callgrade = BUNDLE / "check" / "callgrade.py"
        self.mail = state / "no-mail-file-here.jsonl"   # the owner's emails cannot be seen here (on the Mac the file is dead since 12 Nov)
        self.mail_wait = 180.0
        self.mail_fresh = 86400.0
        self.speed_async = False


def slug_of(name: str) -> str:   # keeper/tick.py _slug
    return re.sub(r"[^a-z0-9]+", "-", name.lower().split("'")[0]).strip("-") or "line"


def card_id(watch_slug: str, p: dict) -> str:   # keeper/cards.py card_id
    if p["sort"] == "WALL":
        return f"{watch_slug}-wall-speed"
    return f"{watch_slug}-{p['sort'].lower().replace(' ', '-')}-{p['slug']}"


def accounts() -> list:   # keeper/walls.py accounts(), from the snapshot
    out = []
    for line in (BUNDLE / "snapshot" / "llm-accounts.txt").read_text().splitlines():
        parts = line.split()
        if len(parts) == 2:
            try:
                out.append((datetime.strptime(parts[0], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp(), parts[1]))
            except ValueError:
                continue
    return sorted(out)


def paying_at(accts: list, t: float):   # keeper/walls.py paying_at
    now = [a for s, a in accts if s <= t]
    return now[-1] if now else None


# ---- rec-drop, read-only ----
class RecDrop:
    def __init__(self, url: str, key: str, seal: str | None):
        self.url, self.key = url.rstrip("/"), key
        self.seal = None
        if seal:
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM
            self.seal = AESGCM(base64.b64decode(seal.strip()))

    def _get(self, path: str):
        r = urllib.request.Request(self.url + path, method="GET", headers={"X-Drop-Key": self.key, "User-Agent": "checker-gh/1"})
        try:
            with urllib.request.urlopen(r, timeout=60) as f:
                return f.read()
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            raise

    def names(self) -> list:
        return json.loads(self._get("/list"))["names"]

    def file(self, name: str):
        b = self._get("/f/" + name)
        return None if b is None else self.seal.decrypt(b[:12], b[12:], name.encode())


def folder_for(name: str, others: list) -> str:   # rec_pull.py folder_for: the listed business whose id starts the room
    m = RECNAME.match(name)
    room = m.group(1) if m else ""
    for i in others:
        if room.startswith(i + "-"):
            return i
    return "elijah-line"


def fetch_calls(drop: RecDrop, into: Path, others: list, seen: dict) -> int:
    """Each call whose note (<stem>.json) is listed, not judged yet: its files, unsealed, into <into>/<folder>/ (600). The note
    is written last, as rec-pull does, so a call with its recording still on its way is left for the next run."""
    names = drop.names()
    listed = set(names)
    got = 0
    for n in sorted(x for x in names if x.endswith(".json") and not PART.search(x)):
        stem = n[:-5]
        if refuse.refused(stem) or scrub.label(stem) in seen:
            continue
        d = into / folder_for(n, others)
        d.mkdir(parents=True, exist_ok=True)
        os.chmod(d, 0o700)
        parts = {}
        for ext in (".wav", ".events.jsonl"):
            name = stem + ext
            if name + ".parts" in listed:
                cnt = drop.file(name + ".parts")
                pn = [f"{name}.part{i:03d}" for i in range(int(cnt or 0))]
                if not cnt or not all(p in listed for p in pn):
                    parts = None
                    break
                blobs = [drop.file(p) for p in pn]
                if any(b is None for b in blobs):
                    parts = None
                    break
                parts[name] = b"".join(blobs)
            elif name in listed:
                b = drop.file(name)
                if b is None:
                    parts = None
                    break
                parts[name] = b
            elif ext == ".wav":
                parts = None   # its recording is not there yet
                break
        if parts is None:
            continue
        note = drop.file(n)
        if note is None:
            continue
        settled = time.time() - 120   # a call's files are "finished" once unchanged for 3 s (keeper/calls.py): these are whole already
        for name, data in list(parts.items()) + [(n, note)]:
            p = d / name
            p.write_bytes(data)
            os.chmod(p, 0o600)
            os.utime(p, (settled, settled))
        got += 1
    return got


# ---- judging, as keeper/tick.py does it ----
def judge_folder(cfg: Cfg, watch: dict, folder: Path, seen: dict, now: float, backfill_h: float, only: set | None) -> list:
    out = []
    if not folder.is_dir():
        return out
    found, _ = callmod.finished(folder, now)
    found.sort(key=lambda c: c.robot)
    accts = accounts()
    slug = slug_of(watch["name"])
    for c in found:
        if only is not None and c.label not in only:
            continue
        s = seen.get(c.label, {})
        if s.get("state") in ("judged", "old", "refused"):
            continue
        if not s and backfill_h and now - c.hung_up > backfill_h * 3600:
            seen[c.label] = {"state": "old"}
            continue
        start = c.hung_up - float(c.note.get("seconds") or 0)
        try:
            v = judgemod.apply_skip(judgemod.judge(cfg, c, watch["lines"], watch["defaultLine"], now, account=paying_at(accts, start)),
                                    tuple(watch["skip"]))
        except Exception as e:   # noqa: BLE001 - one call never stops a run
            seen[c.label] = {"state": "broken", "why": type(e).__name__}
            out.append({"call": c.label, "broken": type(e).__name__})
            continue
        if v is None:
            seen[c.label] = {"state": "refused"}
            continue
        v.pop("_names", None)
        (v.get("speed") or {}).pop("ran", None)
        if v["pending"]:
            seen[c.label] = {"state": "pending"}
            out.append({"call": c.label, "pending": True})
            continue
        try:
            raw = c.events.read_bytes() if c.events.exists() else b""
        except OSError:
            raw = b""
        v["lineout"] = b'"from": "lineout"' in raw
        v["rang"] = b"ringowner" in raw
        v["testRecorder"] = b"elijah-rec-test" in raw or "elijah-rec-test" in json.dumps(c.note)
        vd = cfg.state / "verdicts"
        vd.mkdir(parents=True, exist_ok=True)
        tmp = vd / f".{c.label}.json.tmp"
        tmp.write_text(json.dumps(v, indent=1, sort_keys=True))
        os.chmod(tmp, 0o600)
        os.replace(tmp, vd / f"{c.label}.json")
        seen[c.label] = {"state": "judged", "at": v["judgedAt"]}
        out.append({"call": c.label, "robot": v["robot"], "watch": watch["name"],
                    "promises": {k: x.get("result") for k, x in (v.get("promises") or {}).items()},
                    "cards": sorted({card_id(slug, p) for p in v.get("problems") or []})})
    return out


def sentry_send(dsn: str, rows: list) -> int:
    """One event per card a real (non-robot) call opened in this run; fixed words only, digit runs blanked."""
    m = re.match(r"https://([0-9a-f]+)@([^/]+)/(\d+)", dsn or "")
    if not m:
        return 0
    key, host, proj = m.groups()
    sent = 0
    for cid in sorted({c for r in rows if r.get("cards") and not r.get("robot") for c in r["cards"]}):
        sort = next((s for s in LEVEL if cid.split("-", 1)[1].startswith(s.lower().replace(" ", "-"))), "CODE")
        ev = {"event_id": uuid.uuid4().hex, "timestamp": time.time(), "platform": "python", "level": LEVEL.get(sort, "error"),
              "logger": "call-checker", "environment": "call-checker", "server_name": "github",
              "message": {"formatted": re.sub(r"\d{7,}", "[digits]", f"[call checker] {cid} (judged on GitHub: the Mac was away)")},
              "fingerprint": ["keeper-card", cid], "tags": {"card": cid, "sort": sort, "line": "elijah", "from": "github"}}
        r = urllib.request.Request(f"https://{host}/api/{proj}/store/", data=json.dumps(ev).encode(), method="POST",
                                   headers={"Content-Type": "application/json",
                                            "X-Sentry-Auth": f"Sentry sentry_version=7, sentry_client=checker-gh/1, sentry_key={key}"})
        try:
            with urllib.request.urlopen(r, timeout=20):
                sent += 1
        except (urllib.error.URLError, OSError):
            pass
    return sent


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="the call checker's GitHub copy: judge new calls, read-only")
    ap.add_argument("--source", choices=("rec-drop", "dir"), default="rec-drop")
    ap.add_argument("--dir", help="with --source dir: the folder that holds <folder>/<call files> (elijah-line, scripted-line)")
    ap.add_argument("--state", default=str(HERE / "state"))
    ap.add_argument("--summary")
    ap.add_argument("--wait", type=float, default=240.0, help="s to wait inside the run for a pending call")
    ap.add_argument("--all", action="store_true", help="judge old calls too (no 6-hour first-run limit)")
    ap.add_argument("--only", help="a file of labels: judge only these calls")
    ap.add_argument("--peek", action="store_true", help="only count the call notes waiting that are not judged yet (new=N); no install needed")
    ap.add_argument("--grade-py", default=os.environ.get("GRADE_PY") or sys.executable)
    a = ap.parse_args(argv)
    state = Path(a.state).resolve()
    state.mkdir(parents=True, exist_ok=True)
    os.chmod(state, 0o700)
    outbound.use(state)
    cfg = Cfg(state, a.grade_py)
    seen_p = state / "seen.json"
    seen = json.loads(seen_p.read_text()) if seen_p.exists() else {}
    first = not seen
    watches = json.loads((BUNDLE / "snapshot" / "watches.json").read_text())
    others = sorted({x.strip() for x in (BUNDLE / "snapshot" / "other-lines").read_text().splitlines()
                     if re.fullmatch(r"[a-z0-9][a-z0-9-]{1,30}", x.strip()) and not x.strip().startswith(("elijah", "luterson"))},
                    key=lambda x: (-len(x), x))
    only = set(Path(a.only).read_text().split()) if a.only else None
    if a.peek:   # the workflow's first step: with nothing new, the run ends here, before the speed reader is installed
        drop = RecDrop(os.environ["REC_DROP_URL"], os.environ["REC_DROP_READ_KEY"], None)
        new = [n for n in drop.names() if n.endswith(".json") and not PART.search(n) and not refuse.refused(n[:-5])
               and scrub.label(n[:-5]) not in seen]
        print(f"new={len(new)}")
        if os.environ.get("GITHUB_OUTPUT"):
            with open(os.environ["GITHUB_OUTPUT"], "a") as f:
                f.write(f"new={len(new)}\n")
        return 0
    work = None
    if a.source == "dir":
        root = Path(a.dir).resolve()
    else:
        work = Path(tempfile.mkdtemp(prefix="calls-"))
        os.chmod(work, 0o700)
        drop = RecDrop(os.environ["REC_DROP_URL"], os.environ["REC_DROP_READ_KEY"], os.environ["REC_SEAL_KEY"])
        fetch_calls(drop, work, others, seen)
        root = work
    backfill = 0.0 if a.all else (BACKFILL_HOURS if first else 0.0)
    rows = []
    try:
        deadline = time.time() + a.wait
        while True:
            for w in watches:
                rows += [r for r in judge_folder(cfg, w, root / w["folder"], seen, time.time(), backfill, only) if not r.get("pending")]
            backfill = 0.0
            pending = [k for k, s in seen.items() if s.get("state") == "pending"]
            if not pending or time.time() >= deadline:
                break
            time.sleep(min(30.0, max(1.0, deadline - time.time())))
            for k in pending:
                seen.pop(k, None)
    finally:
        if work is not None:
            shutil.rmtree(work, ignore_errors=True)   # the calls' files never stay on the runner
        for d in ("clean", "grade"):   # judge's working copies (clean: the call's events, callers' words in them) never stay either
            shutil.rmtree(state / d, ignore_errors=True)
    tmp = seen_p.with_suffix(".tmp")
    tmp.write_text(json.dumps(seen, sort_keys=True))
    os.replace(tmp, seen_p)
    for r in rows:
        print(r["call"], "BROKE " + r["broken"] if r.get("broken") else (" ".join(r["cards"]) or "PASS"))
    sent = sentry_send(os.environ.get("SENTRY_DSN", ""), rows) if os.environ.get("SENTRY_DSN") else 0
    if a.summary:
        Path(a.summary).write_text(json.dumps(rows, indent=1, sort_keys=True))
    print(f"checker-gh: {len([r for r in rows if not r.get('broken')])} call(s) judged, "
          f"{len([r for r in rows if r.get('broken')])} broke, {sent} Sentry event(s)")
    return 1 if any(r.get("broken") for r in rows) else 0


if __name__ == "__main__":
    raise SystemExit(main())
