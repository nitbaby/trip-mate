"""Run the same questions through single-agent and multi-agent mode and compare cost, speed and grounding.

  .venv/bin/python scripts/compare_modes.py <trip_id> [--url http://localhost:8000] [--only "question substring"]

Each run uses a fresh conversation. LLM calls = latency and rate-limit cost on a free tier.
"""
import argparse
import json
import time
import uuid

import httpx

QUESTIONS = [
    "What time is check-out, and does the hotel include breakfast?",
    "Is my 6 PM flight delayed?",
    "What's the rule for bringing medication into Japan?",
    "Find a vegetarian place near my hotel that's open now.",
    "Add a dinner reservation at 8 PM to tomorrow's itinerary.",
    "What's the weather in Tokyo and what's the check-out time?",
    "What is the Wi-Fi password at the airport lounge?",
]

ap = argparse.ArgumentParser()
ap.add_argument("trip_id")
ap.add_argument("--url", default="http://localhost:8000")
ap.add_argument("--only")
ap.add_argument("--yes", action="store_true", help="allow running against a real LLM (uses your API quota)")
a = ap.parse_args()

health = httpx.get(f"{a.url}/api/health", timeout=10).json()
print(f"target {a.url}: llm_provider={health['llm_provider']} live_mode={health['live_mode']}")
if health["llm_provider"] != "demo" and not a.yes:
    raise SystemExit(f"This backend uses the real '{health['llm_provider']}' LLM: each run costs ~2-8 calls per question per mode "
                     "of your API quota. Re-run with --yes to proceed, or point --url at a backend started with LLM_PROVIDER=demo.")


def run(q: str, mode: str) -> dict:
    t0, ev = time.time(), []
    with httpx.stream("POST", f"{a.url}/api/trips/{a.trip_id}/chat", timeout=180,
                      json={"message": q, "conversationId": uuid.uuid4().hex[:12], "agentMode": mode}) as r:
        r.raise_for_status()
        for line in r.iter_lines():
            if line.startswith("data:"):
                ev.append(json.loads(line[5:]))
    types = [e["type"] for e in ev]
    done = next((e for e in ev if e["type"] == "done"), {})
    err = next((e for e in ev if e["type"] == "error"), None)
    ver = next((e for e in ev if e["type"] == "verified"), None)
    return {
        "secs": round(time.time() - t0, 1), "llm": done.get("llmCalls", "-"), "tools": done.get("toolCalls", "-"),
        "cites": types.count("citation"), "dropped": ver["unsupported"] if ver else 0,
        "conf": next((e["level"] for e in ev if e["type"] == "confidence"), "-"),
        "agents": ",".join(e["agent"] for e in ev if e["type"] == "agent_start") or "-",
        "err": err["message"][:60] if err else "",
    }


rows = []
for q in [q for q in QUESTIONS if not a.only or a.only.lower() in q.lower()]:
    for mode in ("single", "multi"):
        rows.append((q, mode, run(q, mode)))
print(f"{'mode':7}{'secs':>6}{'llm':>5}{'tools':>6}{'cites':>6}{'drop':>5}  {'conf':5} {'agents':28} question")
for q, mode, r in rows:
    print(f"{mode:7}{r['secs']:>6}{r['llm']!s:>5}{r['tools']!s:>6}{r['cites']:>6}{r['dropped']:>5}  {r['conf']:5} {r['agents']:28} {q[:48]} {r['err']}")
for mode in ("single", "multi"):
    rs = [r for _, m, r in rows if m == mode and not r["err"]]
    if rs:
        print(f"\n{mode}: {sum(r['secs'] for r in rs):.0f}s total, {sum(r['llm'] for r in rs if isinstance(r['llm'], int))} LLM calls, "
              f"{sum(r['cites'] for r in rs)} citations, {sum(r['dropped'] for r in rs)} dropped by verifier, {len([1 for _, m, r in rows if m == mode and r['err']])} errors")
