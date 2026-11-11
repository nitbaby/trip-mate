"""LLM_PROVIDER=demo: a deterministic, rule-based stand-in for the model. NOT an AI.

It exists so the UI, the E2E tests and demos run without network, API keys or free-tier rate limits.
It maps the five demo questions (and a few similar ones) to tool calls and composes answers from the
tool results, with [n] citations, so every guardrail and UI path is exercised for real."""
import json
import re
from collections.abc import AsyncIterator
from datetime import date, timedelta


def _field(system: str, rx: str, default: str = "") -> str:
    m = re.search(rx, system)
    return m.group(1) if m else default


def _tool_results(messages: list[dict]) -> list[tuple[str, dict]]:
    """(tool name, parsed result) for tool calls made since the last plain-text user message."""
    start = max(i for i, m in enumerate(messages) if m["role"] == "user" and isinstance(m["content"], str))
    names, out = {}, []
    for m in messages[start + 1:]:
        if isinstance(m["content"], list):
            for b in m["content"]:
                if b["type"] == "tool_use":
                    names[b["id"]] = b["name"]
                elif b["type"] == "tool_result":
                    out.append((names.get(b["tool_use_id"], "?"), json.loads(b["content"])))
    return out


def _time(q: str) -> str:
    m = re.search(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)", q)
    if m:
        h = int(m.group(1)) % 12 + (12 if m.group(3) == "pm" else 0)
        return f"{h:02d}:{m.group(2) or '00'}:00"
    return "19:00:00"


class DemoLLM:
    async def turn(self, system: str, tools: list[dict], messages: list[dict], force_tool: str | None = None) -> AsyncIterator[tuple[str, object]]:
        if "You are the COMPOSER" in system:  # merge specialist answers verbatim (keeps [n] markers)
            body = messages[-1]["content"].split("Specialist answers:\n\n", 1)[-1]
            sections = re.split(r"\n\n(?=\[[A-Z][^\]\n]*\]\n)", body)  # "[Documents agent]\n<answer>" blocks
            text = "\n\n".join(re.sub(r"^\[[^\]\n]*\]\n", "", sec).strip() for sec in sections)
            for w in re.findall(r"\S+\s*", text):
                yield "text", w
            yield "final", {"content": [{"type": "text", "text": text}], "stop_reason": "end_turn"}
            return
        have = {t["name"] for t in tools}
        q = next(m["content"] for m in reversed(messages) if m["role"] == "user" and isinstance(m["content"], str)).lower()
        results = _tool_results(messages)
        text, calls = "", []
        trip_start = _field(system, r"Dates: (\d{4}-\d{2}-\d{2})", "2026-01-01")
        dest = _field(system, r"Destinations: ([^.\n]+?)\.", "Tokyo").split(",")[0]
        today = date.fromisoformat(_field(system, r"it is \w+ (\d{4}-\d{2}-\d{2})", trip_start))

        if not results:
            if re.search(r"\b(add|book|schedule)\b.*\b(reservation|dinner|lunch|meeting)\b", q) and "write_itinerary" in have:
                when = today + timedelta(days=1 if "tomorrow" in q else 0)
                kind = "Lunch" if "lunch" in q else "Dinner"
                calls = [("write_itinerary", {"action": "create", "type": "reservation", "title": f"{kind} reservation",
                                              "start_at": f"{when}T{_time(q)}"})]
            elif re.search(r"\b(vegetarian|restaurant|food|eat|place|places)\b", q) and "search_places" in have:
                calls = [("search_places", {"location": "Shinjuku Granbell Hotel" if "hotel" in q else dest, "vegetarian": "vegetarian" in q, "open_now": "open now" in q})]
            elif ("weather" in q or "forecast" in q) and "get_weather" in have:
                calls = [("get_weather", {"location": dest, "days": 3})]
            elif re.search(r"itinerary|plan today|today's plan", q) and "read_itinerary" in have:
                calls = [("read_itinerary", {})]
            elif "search_docs" in have:
                calls = [("search_docs", {"query": re.sub(r"\b(weather|forecast|temperature|rain)\b", "", q).strip() or q})]
            else:
                text = "I can't help with that part."
        else:
            name, r = results[-1]
            if name == "search_docs" and re.search(r"flight|delay|depart", q) and len(results) == 1 and "get_flight_status" in have:
                blob = " ".join(h["text"] for h in r.get("results", []))
                flights = re.findall(r"Flight:\s*([A-Z]{2}\s?\d+)\s*Departs:[^\n]*?(\d{1,2}:\d{2}\s*[AP]M)", blob)
                want = re.search(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)", q)  # pick the flight departing at the time asked
                key = f"{int(want.group(1))}:{want.group(2) or '00'} {want.group(3).upper()}" if want else None
                pick = next((f for f, t in flights if key and t.replace("  ", " ").lstrip("0") == key), None)
                pick = pick or (flights[0][0] if flights else None)
                if pick:
                    calls = [("get_flight_status", {"flight_number": pick, "date": trip_start})]
            if not calls:
                text = self._answer(name, r, results)
        if text:
            for w in re.findall(r"\S+\s*", text):
                yield "text", w
        blocks = [{"type": "text", "text": text}] if text else []
        for i, (n, a) in enumerate(calls):
            blocks.append({"type": "tool_use", "id": f"demo_{abs(hash((n, i, len(messages)))) % 10**8}", "name": n, "input": a})
        yield "final", {"content": blocks, "stop_reason": "tool_use" if calls else "end_turn"}

    @staticmethod
    def _answer(name: str, r: dict, results: list) -> str:
        if "error" in r:
            return f"I couldn't get that: {r['error']['message']}"
        if name == "search_docs":
            hits = r["results"]
            if not hits:
                return "I couldn't find that in your documents. Please check an official source."
            parts = []
            for h in hits[:2]:
                sentences = re.split(r"(?<=[.!?])\s+|\n+", h["text"])
                text, used = "", []
                for sent in (x.strip() for x in sentences if x.strip()):
                    if len(text) + len(sent) > 240 and used:
                        break
                    used.append(sent)
                    text = " ".join(used)
                parts.append(f"{text} {h['ref']}")
            return "Here is what your documents say:\n\n* " + "\n* ".join(parts)
        if name == "get_flight_status":
            delay = f" It is delayed by {r['delay_minutes']} minutes" if r["delay_minutes"] else " It is on time"
            est = r.get("estimated_departure", "")[11:16]
            gate = f", gate {r['gate']}" if r.get("gate") else ""
            cite = next((f" {h['ref']}" for n, x in results if n == "search_docs" for h in x.get("results", [])[:1]), "")
            return f"Flight {r['flight']}{cite}:{delay}{f', now departing about {est}' if est else ''}{gate}. Last updated {r['last_updated'][:16].replace('T', ' ')} UTC."
        if name == "search_places":
            if not r["results"]:
                return "I couldn't find any matching places right now."
            lines = [f"**{p['name']}** ({p['cuisine']}), {p['distance_m']} m away, rated {p['rating']}" for p in r["results"][:3]]
            return "Here are places near you:\n\n* " + "\n* ".join(lines)
        if name == "get_weather":
            d = r["daily"]
            return f"Forecast for {r['location']}:\n\n* " + "\n* ".join(f"{x['date']}: {x['conditions']}, {x['low_c']}–{x['high_c']}°C" for x in d)
        if name == "read_itinerary":
            items = r["items"]
            return "Your itinerary:\n\n* " + "\n* ".join(f"{i['start_at'][5:16].replace('T', ' ')} {i['title']}" for i in items) if items else "Nothing is planned yet."
        if name == "write_itinerary":
            i = r["item"]
            warn = " Heads up: it overlaps with another item." if r["conflicts_with"] else ""
            return f"Added **{i['title']}** on {i['start_at'][:10]} at {i['start_at'][11:16]}.{warn} You can undo this change."
        return "Done."
