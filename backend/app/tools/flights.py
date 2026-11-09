"""Flight status provider interface. Mock is deterministic; a real provider can be added later."""
import re
from datetime import datetime, timedelta

from ..config import get_settings
from .cache import TTL, cached

# Fixtures. JL 44 is the demo flight (6:00 PM departure) and is delayed in mock mode.
MOCK = {
    "JL44": {"status": "delayed", "delay_minutes": 35, "gate": "114", "terminal": "3",
             "origin": "LHR", "destination": "HND", "sched": "18:00"},
    "JL43": {"status": "on_time", "delay_minutes": 0, "gate": "62", "terminal": "3",
             "origin": "HND", "destination": "LHR", "sched": "11:55"},
}


def norm(flight_number: str) -> str:
    return re.sub(r"\s+", "", flight_number).upper()


def _mock(fn: str, date: str) -> dict:
    f = MOCK.get(fn) or {"status": "on_time", "delay_minutes": 0, "gate": None, "terminal": None,
                         "origin": None, "destination": None, "sched": None}
    out = {"flight": fn, "date": date, **{k: v for k, v in f.items() if k != "sched"}, "source": "mock"}
    if f["sched"]:
        s = datetime.fromisoformat(f"{date}T{f['sched']}")
        out["scheduled_departure"] = s.isoformat()
        out["estimated_departure"] = (s + timedelta(minutes=f["delay_minutes"])).isoformat()
    return out


def get_flight_status(flight_number: str, date: str) -> dict:
    fn = norm(flight_number)
    if not re.fullmatch(r"[A-Z0-9]{2}\d{1,4}", fn):
        raise ValueError("flight_number must look like 'JL44'")
    datetime.fromisoformat(date)  # validates YYYY-MM-DD
    if get_settings().live_mode == "real":
        raise NotImplementedError("Real flight provider not configured; use LIVE_MODE=mock")
    return cached(f"flight:{fn}:{date}", TTL["flight"], lambda: _mock(fn, date))
