from __future__ import annotations
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from . import refuse, scrub
SETTLE = 3.0

@dataclass
class Call:
    stem: str
    dir: Path
    label: str
    note: dict
    hung_up: float

    @property
    def wav(self) -> Path:
        return self.dir / (self.stem + '.wav')

    @property
    def events(self) -> Path:
        return self.dir / (self.stem + '.events.jsonl')

    @property
    def robot(self) -> bool:
        return '-robot-' in self.stem

def finished(folder: Path, now: float) -> tuple:
    out, refused = ([], 0)
    for note in Path(folder).glob('*.json'):
        if note.name.endswith('.events.jsonl') or not note.name[:8].isdigit():
            continue
        stem = note.name[:-5]
        if refuse.refused(stem):
            refused += 1
            continue
        parts = [p for p in (note, folder / (stem + '.wav'), folder / (stem + '.events.jsonl')) if p.exists()]
        newest = max((p.stat().st_mtime for p in parts))
        if now - newest < SETTLE or (not (folder / (stem + '.events.jsonl')).exists() and now - newest < 60):
            continue
        try:
            d = json.loads(note.read_text())
            start = datetime.fromisoformat(d['startedUtc']).timestamp()
            hung = start + float(d.get('seconds') or 0)
        except (OSError, ValueError, KeyError, TypeError):
            d, hung = ({}, note.stat().st_mtime)
        if refuse.refused(d.get('room')):
            refused += 1
            continue
        out.append(Call(stem, Path(folder), scrub.label(stem), d, hung))
    out.sort(key=lambda c: c.hung_up, reverse=True)
    return (out, refused)
