from __future__ import annotations
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
PACIFIC = ZoneInfo('America/Los_Angeles')

def pacific(t: float, now: float | None=None) -> str:
    d = datetime.fromtimestamp(t, timezone.utc).astimezone(PACIFIC)
    clock = d.strftime('%I:%M %p').lstrip('0')
    if now is not None and datetime.fromtimestamp(now, timezone.utc).astimezone(PACIFIC).date() == d.date():
        return clock
    return f"{d.strftime('%a')} {d.day} {d.strftime('%b')}, {clock}"
