"""Sample trips under samples/<trip>/ (trip.json + documents): the data must be consistent, or demos and evals built on it mislead."""
import datetime as dt
import json
import re
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from app.ingest.mask import redact

SAMPLES = Path(__file__).resolve().parents[2] / "samples"
TRIPS = sorted(p.parent.name for p in SAMPLES.glob("*/trip.json"))
WEEKDAYS = "Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday"
MONTHS = "January|February|March|April|May|June|July|August|September|October|November|December"


def spec(trip: str) -> dict:
    return json.loads((SAMPLES / trip / "trip.json").read_text())


def test_all_sample_trips_have_a_folder():
    assert {"tokyo", "seattle", "delhi"} <= set(TRIPS)
    assert not [p.name for p in SAMPLES.iterdir() if p.is_file() and p.name != "README.md"], "documents belong in a trip folder"


@pytest.mark.parametrize("trip", TRIPS)
def test_manifest_is_valid_and_files_exist(trip):
    s = spec(trip)
    start, end = dt.date.fromisoformat(s["start_date"]), dt.date.fromisoformat(s["end_date"])
    assert start <= end
    ZoneInfo(s["timezone"])  # raises on an unknown timezone
    assert s["destinations"] and s["name"]
    assert len(s["documents"]) == len(set(s["documents"])) >= 4
    for f in s["documents"]:
        assert (SAMPLES / trip / f).stat().st_size > 200, f
    for item in s["itinerary"]:
        day = dt.datetime.fromisoformat(item["start_at"]).date()
        assert start <= day <= end, item
    on_disk = {p.name for p in (SAMPLES / trip).iterdir()} - {"trip.json", "README.md"}
    assert on_disk == set(s["documents"]) | set(s.get("extra_files", [])), "every file in the folder is listed in trip.json, and the reverse"


@pytest.mark.parametrize("trip", TRIPS)
def test_weekday_statements_match_the_calendar(trip):
    """'Friday 12 February 2027' must really be a Friday (the Delhi guide's Taj Mahal Friday trap depends on it)."""
    for p in (SAMPLES / trip).glob("*.txt"):
        for wd, day, month, year in re.findall(rf"\b({WEEKDAYS}),? (\d{{1,2}}) ({MONTHS}) (\d{{4}})", p.read_text()):
            date = dt.datetime.strptime(f"{day} {month} {year}", "%d %B %Y")
            assert date.strftime("%A") == wd, f"{p.name}: {wd} {day} {month} {year} is a {date.strftime('%A')}"


@pytest.mark.parametrize("trip", ["seattle", "delhi"])
def test_new_trips_state_weekdays_so_the_check_above_has_teeth(trip):
    text = " ".join(p.read_text() for p in (SAMPLES / trip).glob("*.txt"))
    assert re.search(rf"\b({WEEKDAYS}),? \d{{1,2}} ({MONTHS}) \d{{4}}", text)


@pytest.mark.parametrize("trip", TRIPS)
def test_sensitive_values_in_samples_are_all_masked(trip):
    """Passports, booking references and card numbers in every sample document must be found by the masker.
    (A 10-digit passport once slipped past the 6-9 character passport pattern: real numbers are 8-9 characters.)"""
    raw = {"passport_number": re.compile(r"(?i)passport\W+((?=[A-Z0-9]*\d)[A-Z0-9]{6,12})\b"),  # must contain a digit: not the word "Canadian"
           "card_number": re.compile(r"\b(\d{4} \d{4} \d{4} \d{4})\b"),
           "booking_reference": re.compile(r"(?i)(?:Booking reference|Confirmation number|PNR):\s*([A-Z0-9]{5,12})\b")}
    seen = 0
    for f in spec(trip)["documents"]:
        text = (SAMPLES / trip / f).read_text()
        cleaned = redact(text)
        for kind, rx in raw.items():
            for m in rx.finditer(text):
                seen += 1
                assert m.group(1) not in cleaned, f"{trip}/{f}: {kind} {m.group(1)!r} is not masked/redacted"
    assert seen >= 4, "the sample trip should contain sensitive values to test masking with"
