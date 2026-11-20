"""Routing-only comparison on the eval set: which specialists does each router pick for each of the 56 questions?

  TRIPMATE_DATA_DIR=/tmp/tm-router .venv/bin/python scripts/eval_router.py [--label gemini] [--only SUBSTR]

Always set TRIPMATE_DATA_DIR to a throwaway dir: the LLM adapter counts requests in that database. The provider/model come from
the usual settings (LLM_PROVIDER, ...). It sends ONE short router request per question (no tools, no documents), then scores:
  rules   the regex router alone (no LLM)
  hybrid  today's default: rules, and the LLM only when no rule matches (ROUTER_MODE=rules + ROUTER_LLM_FALLBACK)
  llm     the LLM routes every question (ROUTER_MODE=llm); an unusable reply keeps the rules' route
Expected routes are DERIVED from each case's own checks (a live tool in tools_any -> live, read_itinerary/write -> itinerary,
cite/refuse/document categories -> docs): an approximation, not a hand-labelled truth. 'exact' = same set of specialists;
'covers' = every expected specialist was chosen (extras cost an extra agent but are not wrong)."""
import argparse
import asyncio
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.agent.llm import LLMError, build_llm, missing_key_message
from app.agent.router import ROUTER_PROMPT, matched_any, parse_intents, route, widen_fallback
from app.config import get_settings

LIVE_TOOLS = {"get_flight_status", "get_weather", "search_places", "convert_currency"}
ORDER = ["docs", "live", "itinerary"]


def expected(case: dict) -> list[str]:
    tools = set(case.get("tools_any", [])) | set(case.get("tools_all", []))
    out = set()
    if tools & LIVE_TOOLS:
        out.add("live")
    if "read_itinerary" in tools or "write" in case or case["category"] in ("itinerary", "itinerary_write"):
        out.add("itinerary")
    if case.get("cite") or case.get("refuse") or "search_docs" in tools or case["category"] in ("doc_fact", "doc_multi", "not_in_docs", "sensitive"):
        out.add("docs")
    return [a for a in ORDER if a in out] or ["docs"]


async def ask(llm, question: str) -> tuple[list[str], bool]:
    """(intents, usable): usable is False when the reply had no JSON object or the call failed."""
    text = ""
    try:
        async for kind, payload in llm.turn(ROUTER_PROMPT, [], [{"role": "user", "content": f"Latest message: {question}"}]):
            if kind == "text":
                text += payload
    except LLMError:
        return [], False
    return widen_fallback(parse_intents(text)), bool(re.search(r"\{.*\}", text, re.DOTALL))


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", default="router")
    ap.add_argument("--only", help="comma-separated substrings of case ids or categories")
    ap.add_argument("--out")
    a = ap.parse_args()
    s = get_settings()
    llm = build_llm(s)
    if llm is None or s.llm_provider == "demo":
        sys.exit(missing_key_message(s) or "Set a real LLM provider.")
    cases = json.load(open(Path(__file__).resolve().parents[1] / "eval" / "questions.json"))["cases"]
    if a.only:
        keys = a.only.split(",")
        cases = [c for c in cases if any(k in c["id"] or k in c["category"] for k in keys)]
    print(f"provider={s.llm_provider} model={llm.model} label={a.label} questions={len(cases)}")
    rows = []
    for i, c in enumerate(cases, 1):
        q, exp, rules = c["question"], expected(c), route(c["question"])
        llm_route, usable = await ask(llm, q)
        llm_final = llm_route if usable else rules                    # ROUTER_MODE=llm
        hybrid = rules if matched_any(q) else (llm_route if usable else rules)  # default: LLM only on a miss
        rows.append({"id": c["id"], "category": c["category"], "question": q, "expected": exp, "rules": rules, "hybrid": hybrid,
                     "llm": llm_final, "llm_usable": usable, "matched_by_rule": matched_any(q)})
        print(f"{i:2}/{len(cases)} {c['id']:20} exp={exp} rules={rules} llm={llm_final}{'' if usable else ' (unusable reply)'}", flush=True)
    print(f"\n{'router':8} {'exact':>9} {'covers':>9} {'avg agents':>11}")
    summary = {}
    for mode in ("rules", "hybrid", "llm"):
        ex = sum(set(r[mode]) == set(r["expected"]) for r in rows)
        cv = sum(set(r["expected"]) <= set(r[mode]) for r in rows)
        ag = sum(len(r[mode]) for r in rows) / len(rows)
        summary[mode] = {"exact": ex, "covers": cv, "avg_agents": round(ag, 2)}
        print(f"{mode:8} {ex:>4}/{len(rows):<4} {cv:>4}/{len(rows):<4} {ag:>11.2f}")
    print(f"unusable LLM replies: {sum(not r['llm_usable'] for r in rows)}")
    print("\nwhere the LLM router differs from the expected route:")
    for r in rows:
        if set(r["llm"]) != set(r["expected"]):
            print(f"  {r['id']:20} expected={r['expected']} llm={r['llm']} rules={r['rules']} | {r['question'][:60]}")
    out = a.out or str(Path(__file__).resolve().parents[1] / "eval" / "results" / f"router-{a.label}.json")
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    json.dump({"label": a.label, "model": llm.model, "summary": summary, "rows": rows}, open(out, "w"), indent=1)
    print("wrote", out)


asyncio.run(main())
