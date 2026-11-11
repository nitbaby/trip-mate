"""Retrieval-only eval (no LLM): does the right chunk come back, at what rank and score, and which confidence level results?

  TRIPMATE_DATA_DIR=<copy of a data dir that holds the EVAL trip> .venv/bin/python scripts/eval_retrieval.py [--trip ID] [-k 5]

For every eval question with expected text (`all`) it finds the first retrieved chunk containing the expected text
(for multi-fact questions: every entry), and for `not_in_docs` questions it shows the top score (these should end up
low/none). Then it sweeps the three confidence thresholds and prints how many answerable questions would be rated
high / low / none and how many unanswerable ones would wrongly be rated high. Read-only; use a COPY of the data dir."""
import argparse
import itertools
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
from app import vectors  # noqa: E402
from app.config import get_settings  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--trip")
ap.add_argument("-k", type=int, default=5)
a = ap.parse_args()
s = get_settings()
trip = a.trip
if not trip:
    c = sqlite3.connect(f"file:{Path(s.tripmate_data_dir) / 'tripmate.db'}?mode=ro", uri=True)
    trip = c.execute("SELECT id FROM trips WHERE name LIKE 'EVAL%' ORDER BY created_at DESC LIMIT 1").fetchone()[0]
cases = json.loads((ROOT / "eval" / "questions.json").read_text())["cases"]


def level(hits, high, agree, low):
    strong = [h for h in hits if h["score"] >= low]
    if not strong:
        return "none"
    top = strong[0]
    if top["score"] >= high or (top["score"] >= agree and any(h["document_id"] == top["document_id"] and h is not top for h in strong[1:])):
        return "high"
    return "low"


def contains(text, entry):
    t = text.lower()
    return any(x.strip().lower() in t for x in entry.split("|"))


pos, neg = [], []
print(f"trip {trip}, embedder {s.embeddings}, k={a.k}\n{'id':<20}{'rank':>5}{'top':>7}{'hit':>7}  level(now)")
for k in cases:
    want = [e for e in k.get("all", []) if k["category"] in ("doc_fact", "doc_multi")]
    if not want and k["category"] != "not_in_docs":
        continue
    hits = vectors.query(trip, k["question"], k=a.k)
    top = hits[0]["score"] if hits else 0
    if k["category"] == "not_in_docs":
        neg.append(hits)
        print(f"{k['id']:<20}{'-':>5}{top:>7.3f}{'-':>7}  {level(hits, s.conf_high, s.conf_agree, s.conf_low)} (should not be high)")
        continue
    ranks = []
    for e in want:
        r = next((i for i, h in enumerate(hits) if contains(h["text"], e)), None)
        ranks.append(r)
    rank = None if None in ranks else max(ranks)
    hs = hits[rank]["score"] if rank is not None else 0
    pos.append((hits, rank))
    print(f"{k['id']:<20}{('miss' if rank is None else rank + 1):>5}{top:>7.3f}{hs:>7.3f}  {level(hits, s.conf_high, s.conf_agree, s.conf_low)}")

print(f"\nanswerable: {len(pos)} questions, answer chunk in top-{a.k}: {sum(r is not None for _, r in pos)}, in top-3: {sum(r is not None and r < 3 for _, r in pos)}")
print(f"\n{'high':>5}{'agree':>6}{'low':>5} | answerable: high  low none, answer-chunk-returned | unanswerable rated high / low / none")
for high, agree, low in itertools.product([0.40, 0.45, 0.50, 0.55], [0.30, 0.35, 0.40], [0.15, 0.20, 0.25, 0.30]):
    if not low < agree < high:
        continue
    lv = [level(h, high, agree, low) for h, _ in pos]
    ret = sum(1 for (h, r), l in zip(pos, lv) if r is not None and h[r]["score"] >= low - s.conf_sibling_margin and l != "none")
    nl = [level(h, high, agree, low) for h in neg]
    mark = "  <- current" if (high, agree, low) == (s.conf_high, s.conf_agree, s.conf_low) else ""
    print(f"{high:>5}{agree:>6}{low:>5} | {lv.count('high'):>16}{lv.count('low'):>5}{lv.count('none'):>5}{ret:>6}/{len(pos)} | {nl.count('high')} / {nl.count('low')} / {nl.count('none')}{mark}")
