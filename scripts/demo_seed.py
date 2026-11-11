"""Create the demo trip on a running backend: trip + the four sample documents (+ optional itinerary item).

  .venv/bin/python scripts/demo_seed.py [--url http://localhost:8010] [--with-itinerary]

Prints the trip id and the UI link. Point --url at a demo backend started with its OWN data dir
(see docs/DEMO_PLAN.md); the default is :8010 so it never lands in your day-to-day data on :8000 by accident."""
import argparse
import sys
import time
from pathlib import Path

import httpx

ap = argparse.ArgumentParser()
ap.add_argument("--url", default="http://localhost:8010")
ap.add_argument("--ui", default="http://localhost:5180", help="only used to print the link")
ap.add_argument("--with-itinerary", action="store_true", help="also add 'Japanese Garden Visit' on 1 Dec 10:00 (for the plan question)")
a = ap.parse_args()
samples = Path(__file__).resolve().parent.parent / "samples"
c = httpx.Client(base_url=a.url, timeout=30)
try:
    c.get("/api/health").raise_for_status()
except httpx.HTTPError as e:
    sys.exit(f"Backend not reachable at {a.url}: {e}")

trip = c.post("/api/trips", json={"name": "Tokyo Dec 2026", "destinations": ["Tokyo"], "start_date": "2026-11-30",
                                  "end_date": "2026-12-06", "timezone": "Asia/Tokyo"}).json()
tid = trip["id"]
ids = []
for f in ["hotel_confirmation.txt", "flight_itinerary.txt", "japan_entry_rules.txt", "tokyo_guide.md"]:
    with open(samples / f, "rb") as fh:
        ids.append((f, c.post(f"/api/trips/{tid}/documents", files={"file": (f, fh)}).json()["id"]))
for f, d in ids:
    for _ in range(60):
        st = c.get(f"/api/trips/{tid}/documents/{d}/status").json()
        if st["status"] in ("ready", "failed"):
            break
        time.sleep(1)
    print(f"  {f}: {st['status']} ({st.get('doc_type')})")
if a.with_itinerary:
    c.post(f"/api/trips/{tid}/itinerary", json={"type": "activity", "title": "Japanese Garden Visit",
                                                 "start_at": "2026-12-01T10:00:00", "location": "Tokyo"}).raise_for_status()
    print("  itinerary: Japanese Garden Visit, 2026-12-01 10:00")
print(f"trip id: {tid}\nUI: {a.ui}/trips/{tid}/chat")
