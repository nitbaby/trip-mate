"""Chat with a running backend from the terminal and watch the typed events.

  .venv/bin/python scripts/chat_cli.py <trip_id> "What time is check-out?" [--cid conv1] [--url http://localhost:8000]
"""
import argparse
import json

import httpx

ap = argparse.ArgumentParser()
ap.add_argument("trip_id")
ap.add_argument("message")
ap.add_argument("--cid")
ap.add_argument("--url", default="http://localhost:8000")
a = ap.parse_args()

with httpx.stream("POST", f"{a.url}/api/trips/{a.trip_id}/chat", timeout=120,
                  json={"message": a.message, "conversationId": a.cid}) as r:
    if r.status_code != 200:
        print(r.read().decode())
        raise SystemExit(1)
    for line in r.iter_lines():
        if not line.startswith("data:"):
            continue
        e = json.loads(line[5:])
        t = e["type"]
        if t == "token":
            print(e["text"], end="", flush=True)
        elif t == "tool_start":
            print(f"\n  [tool] {e['label']} ({e['name']})")
        elif t == "tool_result":
            print(f"  [tool] {'ok' if e['ok'] else 'FAILED'}: {e['summary']}")
        elif t == "citation":
            print(f"\n  [source {e['marker']}] {e['label']}")
        elif t == "confidence":
            print(f"\n  [confidence] {e['level']}")
        elif t == "verify":
            print(f"  [verify] {e['reason']}")
        elif t == "itinerary_updated":
            print(f"\n  [itinerary] {e['action']} {e['itemId']} (undo id: {e.get('undoId')})")
        elif t == "error":
            print(f"\n  [error] {e['code']}: {e['message']} (retryable={e['retryable']})")
        elif t == "done":
            print(f"\n  [done] message {e['messageId']}")
