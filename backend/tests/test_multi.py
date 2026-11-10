import json
import time

import pytest
from app.agent.router import route
from app.agent.verify import verify_citations

from tests.fakes import ScriptedLLM
from tests.test_agent import HOTEL, Q_HOTEL, RULES, types

FLIGHT = (b"Passenger: A\nFlight: JL 44\nDeparts: London Heathrow, 30 November 2026, 6:00 PM\n"
          b"Check-in closes 60 minutes before departure.\n")


@pytest.fixture
def trip(client):
    tid = client.post("/api/trips", json={"name": "Tokyo", "destinations": ["Tokyo"], "start_date": "2026-11-30",
                                          "end_date": "2026-12-06", "timezone": "Asia/Tokyo"}).json()["id"]
    for name, data in (("hotel.txt", HOTEL), ("rules.txt", RULES), ("flight.txt", FLIGHT)):
        did = client.post(f"/api/trips/{tid}/documents", files={"file": (name, data)}).json()["id"]
        for _ in range(50):
            if client.get(f"/api/trips/{tid}/documents/{did}/status").json()["status"] == "ready":
                break
            time.sleep(0.1)
    return tid


def chat(client, tid, message, llm, cid=None):
    client.app.state.llm = llm
    events = []
    with client.stream("POST", f"/api/trips/{tid}/chat", json={"message": message, "conversationId": cid, "agentMode": "multi"}) as r:
        assert r.status_code == 200
        for line in r.iter_lines():
            if line.startswith("data:"):
                events.append(json.loads(line[5:]))
    return events


# ---------- router ----------
@pytest.mark.parametrize("q,expected", [
    ("What time is check-out, and does the hotel include breakfast?", ["docs"]),
    ("Is my 6 PM flight delayed?", ["live"]),
    ("What's the rule for bringing medication into Japan?", ["docs"]),
    ("Find a vegetarian place near my hotel that's open now.", ["live"]),
    ("Add a dinner reservation at 8 PM to tomorrow's itinerary.", ["itinerary"]),
    ("What's on my itinerary today?", ["itinerary"]),
    ("What's the weather in Tokyo and what's the check-out time?", ["docs", "live"]),
    ("hi", ["docs"]),
    ("What is the Wi-Fi password at the airport lounge?", ["docs"]),
])
def test_router(q, expected):
    assert route(q) == expected


# ---------- verifier ----------
def test_verifier_flags_wrong_numbers_and_wrong_passages():
    refs = {1: {"text": "Check-out: 11:00 AM on 6 December 2026\nBreakfast is included, served daily 6:30 AM to 10:00 AM"},
            2: {"text": "Wi-Fi is free in all rooms."}}
    assert verify_citations("Check-out is at 11:00 AM [1].", refs) == {"1": True}
    assert verify_citations("Check-out is at 9:00 AM [1].", refs) == {"1": False}        # number not in evidence
    assert verify_citations("The pool opens at sunrise [2].", refs) == {"2": False}      # wrong passage
    flight = {1: {"text": "Flight: JL 44 Departs: London Heathrow 6:00 PM"}}
    claim = "Flight JL 44 is delayed 35 minutes [1]."
    assert verify_citations(claim, flight) == {"1": False}  # the delay is not in the passage...
    live = ['{"delay_minutes": 35, "status": "delayed"}']
    assert verify_citations(claim, flight, evidence=live) == {"1": True}  # ...but is in the live tool result


def test_verifier_real_gemini_answers():
    """Regression: answers recorded from live Gemini that an earlier, stricter verifier wrongly rejected."""
    hotel = {
        1: {"text": "Breakfast is included for up to 2 guests, served daily 6:30 AM to 10:00 AM in the 2nd floor restaurant.\n"
                    "Late check-out until 1:00 PM is available for 3,000 JPY, subject to availability."},
        2: {"text": "Check-in: 3:00 PM on 1 December 2026\nCheck-out: 11:00 AM on 6 December 2026\nRoom: Superior Double"},
    }
    two_facts = ("Check-out is at 11:00 AM [2], and breakfast is included for up to 2 guests, served daily from "
                 "6:30 AM to 10:00 AM in the 2nd-floor restaurant [1].")
    assert verify_citations(two_facts, hotel) == {"1": True, "2": True}
    # swapping the markers must fail: each half now points at the wrong passage
    swapped = two_facts.replace("[2]", "[X]").replace("[1]", "[2]").replace("[X]", "[1]")
    assert verify_citations(swapped, hotel) == {"1": False, "2": False}

    flight = {2: {"text": "Flight: JL 44\nDeparts: London Heathrow (LHR) Terminal 3, 30 November 2026, 6:00 PM"}}
    live = [('{"flight": "JL44", "status": "delayed", "delay_minutes": 35, "gate": "114", "terminal": "3", '
            '"scheduled_departure": "2026-11-30T18:00:00", "estimated_departure": "2026-11-30T18:35:00"}')]
    answer = ("Your 6:00 PM flight **JL 44** from London Heathrow is currently **delayed by 35 minutes** [2].\n"
              "* **Estimated Departure:** 6:35 PM (Gate 114, Terminal 3) [2]")
    assert verify_citations(answer, flight, evidence=live) == {"2": True}
    assert verify_citations("Estimated departure is 7:10 PM [2].", flight, evidence=live) == {"2": False}  # invented time


# ---------- single specialist ----------
def _hash_friendly_prefetch(monkeypatch):
    """Tests use the hash embedder, which scores long natural-language queries low: prefetch a keyword query instead."""
    monkeypatch.setattr("app.agent.loop._prefetch", lambda agent, msg: Q_HOTEL if agent == "docs" else None)


def test_docs_agent_answers_directly_with_verified_citation(client, trip, monkeypatch):
    _hash_friendly_prefetch(monkeypatch)
    llm = ScriptedLLM([{"text": "Check-out is 11:00 AM and breakfast is included [1]."}])  # search_docs is prefetched
    ev = chat(client, trip, "What time is check-out, and does the hotel include breakfast?", llm)
    t = types(ev)
    assert t[0] == "agent_start" and ev[0]["agent"] == "docs" and ev[0]["label"] == "Documents agent"
    assert all(e.get("agent") == "docs" for e in ev if e["type"] in ("tool_start", "tool_result"))
    assert "agent_end" in t and t[-1] == "done"
    assert next(e for e in ev if e["type"] == "verified") == {"type": "verified", "checked": 1, "unsupported": 0}
    assert "citation" in t and next(e for e in ev if e["type"] == "confidence")["level"] == "high"
    done = ev[-1]
    assert done["agentMode"] == "multi" and done["llmCalls"] == 1 and done["toolCalls"] == 1  # prefetched search, no router/composer calls
    # the docs agent only sees its own tool, with a role-specific prompt
    assert [t["name"] for t in llm.calls[0]["tools"]] == ["search_docs"]
    assert "Documents agent" not in llm.calls[0]["system"] and "documents agent" in llm.calls[0]["system"]


def test_unsupported_citation_is_dropped_and_confidence_lowered(client, trip):
    llm = ScriptedLLM([{"text": "Check-out is at 9:45 PM [1]."}])  # wrong time: not in the passage
    ev = chat(client, trip, "What time is check-out?", llm)
    assert next(e for e in ev if e["type"] == "verified")["unsupported"] == 1
    assert "citation" not in types(ev)
    assert next(e for e in ev if e["type"] == "confidence")["level"] == "low"


def test_live_agent_has_live_tools_and_docs_lookup(client, trip):
    llm = ScriptedLLM([{"tools": [("get_flight_status", {"flight_number": "JL44", "date": "2026-11-30"})]},
                       {"text": "JL 44 is delayed by 35 minutes."}])
    ev = chat(client, trip, "Is my 6 PM flight delayed?", llm)
    assert ev[0]["agent"] == "live"
    assert {t["name"] for t in llm.calls[0]["tools"]} == {"search_docs", "get_flight_status", "get_weather",
                                                              "search_places", "convert_currency"}
    assert [e["summary"] for e in ev if e["type"] == "tool_result"][1] == "JL44 delayed by 35 min"


def test_agent_cannot_call_tools_outside_its_allowlist(client, trip):
    llm = ScriptedLLM([{"tools": [("write_itinerary", {"action": "create", "type": "note", "title": "x",
                                                      "start_at": "2026-12-02T20:00:00"})]},
                       {"text": "I can't change the itinerary."}])
    ev = chat(client, trip, "What does my hotel confirmation say?", llm)  # routed to docs
    tr = [e for e in ev if e["type"] == "tool_result"][-1]
    assert tr["ok"] is False and "not available" in tr["summary"]
    assert client.get(f"/api/trips/{trip}/itinerary").json() == []
    assert "itinerary_updated" not in types(ev)


def test_itinerary_agent_writes_with_undo(client, trip):
    llm = ScriptedLLM([{"tools": [("write_itinerary", {"action": "create", "type": "reservation", "title": "Dinner",
                                                      "start_at": "2026-12-02T20:00:00"})]},
                       {"text": "Added dinner. You can undo it."}])
    ev = chat(client, trip, "Add a dinner reservation at 8 PM tomorrow", llm)
    assert ev[0]["agent"] == "itinerary"
    up = next(e for e in ev if e["type"] == "itinerary_updated")
    assert client.post(f"/api/trips/{trip}/undo/{up['undoId']}").status_code == 200
    assert "confidence" not in types(ev)


# ---------- compound question: parallel specialists + composer ----------
def test_compound_question_runs_specialists_then_composer(client, trip, monkeypatch):
    _hash_friendly_prefetch(monkeypatch)
    docs_turns = [{"text": "Check-out is 11:00 AM [1]."}]
    live_turns = [{"tools": [("get_weather", {"location": "Tokyo", "days": 2})]}, {"text": "Tokyo will be clear, 13C."}]

    class Router:  # dispatch by system prompt so parallel ordering doesn't matter
        def __init__(self):
            self.docs, self.live, self.composer_input = ScriptedLLM(docs_turns), ScriptedLLM(live_turns), None
            self.calls = []

        async def turn(self, system, tools, messages):
            self.calls.append(system[:40])
            if "COMPOSER" in system:
                self.composer_input = messages[-1]["content"]
                agen = ScriptedLLM([{"text": "Check-out is 11:00 AM [1]. Tokyo will be clear, 13C."}]).turn(system, tools, messages)
            else:
                agen = (self.docs if "documents agent" in system else self.live).turn(system, tools, messages)
            async for x in agen:
                yield x

    llm = Router()
    ev = chat(client, trip, "What's the weather in Tokyo and what's the check-out time?", llm)
    t = types(ev)
    starts = [e["agent"] for e in ev if e["type"] == "agent_start"]
    assert set(starts[:2]) == {"docs", "live"} and starts[2] == "composer"
    assert t.index("agent_start") < t.index("tool_start")
    # specialist text is NOT streamed to the user; only the composer's answer is
    streamed = "".join(e["text"] for e in ev if e["type"] == "token")
    assert streamed == "Check-out is 11:00 AM [1]. Tokyo will be clear, 13C."
    assert "Documents agent" in llm.composer_input and "Live info agent" in llm.composer_input
    assert "[1]" in llm.composer_input  # citation markers pass through to the composer
    assert next(e for e in ev if e["type"] == "verified")["unsupported"] == 0
    assert ev[-1]["llmCalls"] == 4 and ev[-1]["toolCalls"] == 2  # docs: prefetched search + answer; live: 2; composer: 1


def test_failure_in_one_specialist_ends_the_turn_with_an_error(client, trip):
    from app.agent.llm import LLMError

    class Boom:
        async def turn(self, system, tools, messages):
            raise LLMError("Gemini rate limit reached. Wait and retry.", True)
            yield  # pragma: no cover

    ev = chat(client, trip, "What's the weather in Tokyo and what's the check-out time?", Boom())
    assert ev[-1]["type"] == "error" and ev[-1]["retryable"] is True and "done" not in types(ev)


def test_multi_is_the_default_mode_and_single_still_available(client, trip, monkeypatch):
    from app import config

    monkeypatch.delenv("AGENT_MODE", raising=False)
    config.get_settings.cache_clear()
    assert config.get_settings().agent_mode == "multi"
    client.app.state.llm = ScriptedLLM([{"text": "hello"}])
    with client.stream("POST", f"/api/trips/{trip}/chat", json={"message": "hi", "agentMode": "single"}) as r:
        evs = [json.loads(line[5:]) for line in r.iter_lines() if line.startswith("data:")]
    assert evs[-1]["agentMode"] == "single" and "agent_start" not in types(evs)
    assert client.post(f"/api/trips/{trip}/chat", json={"message": "hi", "agentMode": "bogus"}).status_code == 422


# ---------- small-model safeguards ----------
def test_docs_agent_searches_even_if_the_model_would_not(client, trip):
    llm = ScriptedLLM([{"text": "I couldn't find it in your documents."}])
    ev = chat(client, trip, "What is the wifi password at the airport lounge?", llm)
    names = [e["name"] for e in ev if e["type"] == "tool_start"]
    assert names == ["search_docs"] and ev[-1]["llmCalls"] == 1


def test_failed_itinerary_write_is_never_reported_as_done(client, trip):
    llm = ScriptedLLM([{"tools": [("write_itinerary", {"action": "create", "type": "reservation",
                                                      "start_at": "2026-12-02T20:00:00"})]},  # no title: rejected
                       {"text": "I've added dinner at 8 PM to your itinerary."}])  # the model lies
    ev = chat(client, trip, "Add dinner at 8 PM tomorrow to my itinerary", llm)
    assert [e for e in ev if e["type"] == "tool_result"][-1]["ok"] is False
    said = "".join(e["text"] for e in ev if e["type"] == "token")
    assert "NOT changed" in said
    assert client.get(f"/api/trips/{trip}/itinerary").json() == []
    # the model is told the change did not happen
    assert "NOT changed" in json.dumps(llm.calls[1]["messages"])
