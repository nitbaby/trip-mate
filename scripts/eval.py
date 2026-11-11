"""Run the TripMate eval set (eval/questions.json) against a running backend and score every answer.

  .venv/bin/python scripts/eval.py [--url http://localhost:8010] [--only CATEGORY_OR_ID_SUBSTRING] [--label qwen3-8b]
                                   [--agent-mode multi|single] [--trip TRIP_ID] [--out eval/results/NAME.json]

It creates its OWN trip (name "EVAL ...") with the four sample documents and one itinerary item, so run it against a
throwaway backend started with its own data dir (see docs/EVAL.md). It refuses :8000 (your data) unless --force.
Each question uses a fresh conversation. Checks are plain string/tool/citation rules, no LLM judge: they are
strict on purpose, so read the failure reasons before deciding whether the app or the check is wrong."""
import argparse
import json
import re
import sys
import time
import uuid
from collections import defaultdict
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
REFUSAL = re.compile(
    r"not (found|available|provided|included|specified|mentioned|covered|in (the|your|any))|"
    r"(could|can)(n't|not| not) find|couldn't|unable to (find|locate)|no (information|mention|details|record)|"
    r"(doesn't|does not|don't|do not|isn't|is not) (say|mention|include|contain|specify|have|list|appear|cover|provide)|"
    r"don't have|do not have|not able to", re.I)

ap = argparse.ArgumentParser()
ap.add_argument("--url", default="http://localhost:8010")
ap.add_argument("--only", help="comma-separated substrings of case ids or categories, e.g. hotel,live-delay")
ap.add_argument("--label", default="run", help="name for this run (model), used in the result file name")
ap.add_argument("--agent-mode", choices=["multi", "single"])
ap.add_argument("--trip", help="reuse this trip instead of creating one (must have the sample documents)")
ap.add_argument("--out")
ap.add_argument("--force", action="store_true", help="allow port 8000 (your own data)")
ap.add_argument("--yes", action="store_true", help="allow a real cloud LLM (uses API quota)")
a = ap.parse_args()

if ":8000" in a.url and not a.force:
    sys.exit("Refusing :8000 (your own backend and data). Start a throwaway backend (docs/EVAL.md) or pass --force.")
c = httpx.Client(base_url=a.url, timeout=30)
try:
    health = c.get("/api/health").json()
except httpx.HTTPError as e:
    sys.exit(f"Backend not reachable at {a.url}: {e}")
if health["llm_provider"] in ("gemini", "anthropic") and not a.yes:
    sys.exit(f"'{health['llm_provider']}' is a cloud LLM: the full set uses ~100 requests. Re-run with --yes to proceed.")
mock = health["live_mode"] == "mock"
print(f"target {a.url}: llm_provider={health['llm_provider']} live_mode={health['live_mode']} label={a.label}")

cases = json.loads((ROOT / "eval" / "questions.json").read_text())["cases"]
only = [x.strip().lower() for x in (a.only or "").split(",") if x.strip()]
cases = [k for k in cases if not only or any(x in k["id"].lower() or x in k["category"].lower() for x in only)]

if a.trip:
    trip = a.trip
else:
    trip = c.post("/api/trips", json={"name": f"EVAL {a.label}", "destinations": ["Tokyo"], "start_date": "2026-11-30",
                                      "end_date": "2026-12-06", "timezone": "Asia/Tokyo"}).json()["id"]
    docs = []
    for f in ["hotel_confirmation.txt", "flight_itinerary.txt", "japan_entry_rules.txt", "tokyo_guide.md"]:
        with open(ROOT / "samples" / f, "rb") as fh:
            docs.append(c.post(f"/api/trips/{trip}/documents", files={"file": (f, fh)}).json()["id"])
    for d in docs:
        for _ in range(90):
            if c.get(f"/api/trips/{trip}/documents/{d}/status").json()["status"] in ("ready", "failed"):
                break
            time.sleep(1)
    c.post(f"/api/trips/{trip}/itinerary", json={"type": "activity", "title": "Japanese Garden Visit",
                                                  "start_at": "2026-12-01T10:00:00", "location": "Tokyo"}).raise_for_status()
    print(f"created trip {trip} with 4 documents and 1 itinerary item")


def itinerary() -> list[dict]:
    return c.get(f"/api/trips/{trip}/itinerary").json()


def ask(q: str) -> dict:
    body = {"message": q, "conversationId": uuid.uuid4().hex[:12]}
    if a.agent_mode:
        body["agentMode"] = a.agent_mode
    t0, ev = time.time(), []
    with httpx.stream("POST", f"{a.url}/api/trips/{trip}/chat", timeout=600, json=body) as r:
        if r.status_code != 200:
            return {"error": f"HTTP {r.status_code}", "secs": 0, "text": "", "tools": [], "cites": [], "conf": "-", "llm": 0}
        for line in r.iter_lines():
            if line.startswith("data:"):
                ev.append(json.loads(line[5:]))
    done = next((e for e in ev if e["type"] == "done"), {})
    err = next((e for e in ev if e["type"] == "error"), None)
    return {"secs": round(time.time() - t0, 1), "text": "".join(e.get("text", "") for e in ev if e["type"] == "token"),
            "tools": [e["name"] for e in ev if e["type"] == "tool_start"], "cites": [e.get("label", "") for e in ev if e["type"] == "citation"],
            "conf": next((e["level"] for e in ev if e["type"] == "confidence"), "-"), "llm": done.get("llmCalls", 0),
            "error": err["message"][:120] if err else ""}


def has(text: str, entry: str) -> bool:
    t = text.lower().replace(" ", " ").replace(" ", " ")
    return any(alt.strip().lower() in t for alt in entry.split("|"))


def score(k: dict, r: dict, new_items: list[dict]) -> list[str]:
    why = []
    if r.get("error"):
        return [f"error: {r['error']}"]
    if not r["text"].strip():
        why.append("empty answer")
    if not (k.get("mock_only") and not mock):
        why += [f"missing '{e}'" for e in k.get("all", []) if not has(r["text"], e)]
    why += [f"leaked '{s}'" for s in k.get("none", []) if s.lower() in r["text"].lower().replace(" ", "") or s.lower() in r["text"].lower()]
    if k.get("refuse") and not REFUSAL.search(r["text"]):
        why.append("did not say the info is unavailable")
    if k.get("cite") and not any(k["cite"].lower() in x.lower() for x in r["cites"]):
        why.append(f"no citation to '{k['cite']}' (got {r['cites'] or 'none'})")
    if k.get("tools_any") and not set(k["tools_any"]) & set(r["tools"]):
        why.append(f"none of {k['tools_any']} called (got {sorted(set(r['tools'])) or 'none'})")
    why += [f"tool {t} not called" for t in k.get("tools_all", []) if t not in r["tools"]]
    w = k.get("write")
    agent_new = [i for i in new_items if i.get("source") == "agent"]
    if w:
        ok = any(w["title"].lower() in (i["title"] or "").lower() and w["start"] in (i["start_at"] or "") for i in agent_new)
        if not ok:
            why.append(f"expected new item '{w['title']}' at '{w['start']}', got {[(i['title'], i['start_at']) for i in new_items] or 'no change'}")
    elif new_items:
        why.append(f"unexpected itinerary change: {[i['title'] for i in new_items]}")
    return why


results = []
for n, k in enumerate(cases, 1):
    before = {i["id"] for i in itinerary()}
    r = ask(k["question"])
    new_items = [i for i in itinerary() if i["id"] not in before]
    why = score(k, r, new_items)
    results.append({**{x: k[x] for x in ("id", "category", "question")}, "pass": not why, "why": why, **r})
    print(f"{n:>2}/{len(cases)} {'PASS' if not why else 'FAIL'} {r['secs']:>6}s {k['id']:<20} {'; '.join(why)[:150]}", flush=True)

by = defaultdict(lambda: [0, 0])
for r in results:
    by[r["category"]][0] += r["pass"]
    by[r["category"]][1] += 1
tot = sum(r["pass"] for r in results)
print(f"\n{'category':<18}pass")
for cat, (p, n) in by.items():
    print(f"{cat:<18}{p}/{n}")
secs = [r["secs"] for r in results]
print(f"\nTOTAL {tot}/{len(results)} passed · mean {sum(secs) / max(len(secs), 1):.1f}s · max {max(secs, default=0):.0f}s · "
      f"{sum(r['llm'] for r in results)} LLM calls · agent_mode={a.agent_mode or 'server default'}")
out = Path(a.out) if a.out else ROOT / "eval" / "results" / f"{a.label}-{time.strftime('%Y%m%d-%H%M')}.json"
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps({"label": a.label, "health": health, "agent_mode": a.agent_mode, "trip": trip, "passed": tot,
                           "total": len(results), "results": results}, indent=1))
print(f"wrote {out}")
