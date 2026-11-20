"""Create a demo trip on a running backend: trip + its sample documents (+ optional itinerary item).

  .venv/bin/python scripts/demo_seed.py [--trip tokyo|seattle|delhi] [--url http://localhost:8010] [--with-itinerary]

Prints the trip id and the UI link. Point --url at a demo backend started with its OWN data dir
(see docs/DEMO_PLAN.md); the default is :8010 so it never lands in your day-to-day data on :8000 by accident.
Every trip lives in samples/<trip>/ (trip.json + documents); Tokyo is the default."""
import argparse
import json
import sys
import time
from pathlib import Path

import httpx

ap = argparse.ArgumentParser()
ap.add_argument("--trip", default="tokyo", choices=["tokyo", "seattle", "delhi"], help="which sample trip to create (default: tokyo)")
ap.add_argument("--url", default="http://localhost:8010")
ap.add_argument("--ui", default="http://localhost:5180", help="only used to print the link")
ap.add_argument("--with-itinerary", action="store_true", help="also add the trip's sample itinerary item (Tokyo: 'Japanese Garden Visit' on 1 Dec 10:00, for the plan question)")
a = ap.parse_args()
folder = Path(__file__).resolve().parent.parent / "samples" / a.trip  # samples/<trip>/trip.json lists the documents and itinerary items
spec = json.loads((folder / "trip.json").read_text())
c = httpx.Client(base_url=a.url, timeout=30)
try:
    c.get("/api/health").raise_for_status()
except httpx.HTTPError as e:
    sys.exit(f"Backend not reachable at {a.url}: {e}")

trip = c.post("/api/trips", json={k: spec[k] for k in ("name", "destinations", "start_date", "end_date", "timezone")}).json()
tid = trip["id"]
ids = []
for f in spec["documents"]:
    with open(folder / f, "rb") as fh:
        ids.append((f, c.post(f"/api/trips/{tid}/documents", files={"file": (f, fh)}).json()["id"]))
for f, d in ids:
    for _ in range(60):
        st = c.get(f"/api/trips/{tid}/documents/{d}/status").json()
        if st["status"] in ("ready", "failed"):
            break
        time.sleep(1)
    print(f"  {f}: {st['status']} ({st.get('doc_type')})")
if a.with_itinerary:
    for item in spec["itinerary"]:
        c.post(f"/api/trips/{tid}/itinerary", json=item).raise_for_status()
        print(f"  itinerary: {item['title']}, {item['start_at'].replace('T', ' ')[:16]}")
print(f"trip id: {tid}\nUI: {a.ui}/trips/{tid}/chat")
