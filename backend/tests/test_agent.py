import json
import time

import anthropic
import httpx
import pytest

from tests.fakes import ScriptedLLM

HOTEL = (b"Hotel: Shinjuku Granbell Hotel\nConfirmation number: GB7K2941\nPassport: P48213907\n"
         b"Check-in: 3:00 PM\nCheck-out: 11:00 AM\nBreakfast is included for up to 2 guests.\n")
RULES = (b"JAPAN ENTRY RULES: MEDICATION AND CUSTOMS\nMost prescription medicine may be brought into Japan "
         b"for personal use up to a one-month supply. Carry a copy of the prescription.\n")
Q_HOTEL = "Check-out 11:00 AM Breakfast included hotel check-in time"


@pytest.fixture
def trip(client):
    tid = client.post("/api/trips", json={"name": "Tokyo", "destinations": ["Tokyo"], "start_date": "2026-11-30",
                                          "end_date": "2026-12-06", "timezone": "Asia/Tokyo"}).json()["id"]
    for name, data in (("hotel.txt", HOTEL), ("rules.txt", RULES)):
        did = client.post(f"/api/trips/{tid}/documents", files={"file": (name, data)}).json()["id"]
        for _ in range(50):
            if client.get(f"/api/trips/{tid}/documents/{did}/status").json()["status"] == "ready":
                break
            time.sleep(0.1)
    return tid


def chat(client, tid, message, llm, cid=None):
    client.app.state.llm = llm
    events = []
    with client.stream("POST", f"/api/trips/{tid}/chat", json={"message": message, "conversationId": cid}) as r:
        assert r.status_code == 200
        for line in r.iter_lines():
            if line.startswith("data:"):
                events.append(json.loads(line[5:]))
    return events


def types(events):
    return [e["type"] for e in events]


def test_flow1_cited_answer(client, trip):
    llm = ScriptedLLM([{"tools": [("search_docs", {"query": Q_HOTEL})]},
                       {"text": "Check-out is 11:00 AM and breakfast is included [1]."}])
    ev = chat(client, trip, "What time is check-out and is breakfast included?", llm)
    assert types(ev)[0] == "tool_start" and "token" in types(ev) and types(ev)[-1] == "done"
    tr = next(e for e in ev if e["type"] == "tool_result")
    assert tr["ok"] and "confidence high" in tr["summary"]
    cit = next(e for e in ev if e["type"] == "citation")
    assert cit["marker"] == "[1]" and cit["label"].startswith("hotel.txt")
    assert next(e for e in ev if e["type"] == "confidence")["level"] == "high"
    assert "verify" not in types(ev)
    # the Source Drawer endpoint resolves the citation, and sensitive values are masked
    c = client.get(f"/api/documents/{cit['docId']}/chunks/{cit['chunkId']}").json()
    assert "Check-out" in c["text"] and "P48213907" not in str(c)
    # model never saw raw sensitive values, trip_id, or chunk ids
    seen = json.dumps(llm.calls[1]["messages"])
    assert "P48213907" not in seen and "GB7K2941" not in seen and "chunk_id" not in seen
    assert all("trip_id" not in t["input_schema"].get("properties", {}) for t in llm.calls[0]["tools"])
    assert "Asia/Tokyo" in llm.calls[0]["system"]


def test_flow3_medication_verify_badge(client, trip):
    llm = ScriptedLLM([{"tools": [("search_docs", {"query": "bring medication into Japan prescription supply"})]},
                       {"text": "Up to a one-month supply for personal use [1]. Carry the prescription."}])
    ev = chat(client, trip, "What's the rule for bringing medication into Japan?", llm)
    assert next(e for e in ev if e["type"] == "verify")["reason"]
    assert next(e for e in ev if e["type"] == "confidence")["level"] == "high"


def test_not_found_gives_none_confidence_and_no_citation(client, trip):
    llm = ScriptedLLM([{"tools": [("search_docs", {"query": "bake sourdough bread recipe"})]},
                       {"text": "I couldn't find that in your documents. Please check an official source."}])
    ev = chat(client, trip, "How do I bake bread?", llm)
    assert next(e for e in ev if e["type"] == "confidence")["level"] == "none"
    assert "citation" not in types(ev)


def test_answer_without_citation_is_downgraded_to_low(client, trip):
    llm = ScriptedLLM([{"tools": [("search_docs", {"query": Q_HOTEL})]}, {"text": "Check-out is at 11."}])
    ev = chat(client, trip, "check-out?", llm)
    assert next(e for e in ev if e["type"] == "confidence")["level"] == "low"


def test_invented_citation_marker_is_ignored(client, trip):
    llm = ScriptedLLM([{"tools": [("search_docs", {"query": Q_HOTEL})]}, {"text": "Check-out is 11 [7]."}])
    ev = chat(client, trip, "check-out?", llm)
    assert "citation" not in types(ev)
    assert next(e for e in ev if e["type"] == "confidence")["level"] == "low"


def test_flow2_flight_status(client, trip):
    llm = ScriptedLLM([{"tools": [("get_flight_status", {"flight_number": "JL44", "date": "2026-11-30"})]},
                       {"text": "JL 44 is delayed 35 minutes."}])
    ev = chat(client, trip, "Is my 6 PM flight delayed?", llm)
    assert next(e for e in ev if e["type"] == "tool_result")["summary"] == "JL44 delayed by 35 min"
    assert "confidence" not in types(ev)  # live data, no document citation required


def test_flow4_places(client, trip):
    llm = ScriptedLLM([{"tools": [("search_places", {"location": "Shinjuku Granbell Hotel", "vegetarian": True})]},
                       {"text": "Try Ain Soph."}])
    ev = chat(client, trip, "Find a vegetarian place near my hotel", llm)
    assert "place(s) found" in next(e for e in ev if e["type"] == "tool_result")["summary"]


def test_flow5_itinerary_write_and_undo(client, trip):
    llm = ScriptedLLM([{"tools": [("write_itinerary", {"action": "create", "type": "reservation", "title": "Dinner",
                                                       "start_at": "2026-12-02T20:00:00"})]},
                       {"text": "Added dinner. You can undo it."}])
    ev = chat(client, trip, "Add a dinner reservation at 8 PM tomorrow", llm)
    up = next(e for e in ev if e["type"] == "itinerary_updated")
    assert up["action"] == "created" and up["undoId"]
    items = client.get(f"/api/trips/{trip}/itinerary").json()
    assert items[0]["source"] == "agent" and items[0]["id"] == up["itemId"]
    assert client.post(f"/api/trips/{trip}/undo/{up['undoId']}").status_code == 200
    assert client.get(f"/api/trips/{trip}/itinerary").json() == []


def test_model_cannot_override_trip_id(client, trip):
    llm = ScriptedLLM([{"tools": [("search_docs", {"query": Q_HOTEL, "trip_id": "someone-elses-trip"})]},
                       {"text": "ok"}])
    ev = chat(client, trip, "x", llm)
    assert "passage(s)" in next(e for e in ev if e["type"] == "tool_result")["summary"]
    assert not next(e for e in ev if e["type"] == "tool_result")["summary"].startswith("0 passage")


def test_tool_limit_per_turn(client, trip):
    calls = [("convert_currency", {"amount": 1, "from_currency": "USD", "to_currency": "JPY"})] * 7
    llm = ScriptedLLM([{"tools": calls}, {"text": "done"}])
    ev = chat(client, trip, "convert lots", llm)
    results = [e for e in ev if e["type"] == "tool_result"]
    assert [r["ok"] for r in results] == [True] * 6 + [False]
    assert "limit" in results[-1]["summary"].lower()


def test_external_budget_per_session(client, trip, monkeypatch):
    from app import config

    monkeypatch.setenv("MAX_EXTERNAL_CALLS_PER_SESSION", "2")
    config.get_settings.cache_clear()
    one = {"tools": [("convert_currency", {"amount": 1, "from_currency": "USD", "to_currency": "JPY"})]}
    ev = chat(client, trip, "a", ScriptedLLM([one, {"text": "x"}]), cid="sess")
    ev += chat(client, trip, "b", ScriptedLLM([one, {"text": "x"}]), cid="sess")
    ev += chat(client, trip, "c", ScriptedLLM([one, {"text": "x"}]), cid="sess")
    assert [e["ok"] for e in ev if e["type"] == "tool_result"] == [True, True, False]


def test_conversation_history_and_persistence(client, trip):
    first = ScriptedLLM([{"text": "Hello!"}])
    chat(client, trip, "hi", first, cid="c1")
    second = ScriptedLLM([{"text": "Again"}])
    chat(client, trip, "and again", second, cid="c1")
    assert [m["content"] for m in second.calls[0]["messages"]] == ["hi", "Hello!", "and again"]
    msgs = client.get(f"/api/trips/{trip}/conversations/c1/messages").json()
    assert [m["role"] for m in msgs] == ["user", "assistant", "user", "assistant"]
    assert client.get("/api/trips/other/conversations/c1/messages").json() == []


def test_conversation_cannot_cross_trips(client, trip):
    other = client.post("/api/trips", json={"name": "B", "destinations": ["X"], "start_date": "2026-01-01",
                                            "end_date": "2026-01-02"}).json()["id"]
    chat(client, trip, "hi", ScriptedLLM([{"text": "Hello"}]), cid="shared")
    ev = chat(client, other, "hi", ScriptedLLM([{"text": "Hello"}]), cid="shared")
    assert ev[0]["type"] == "error" and not ev[0]["retryable"]


def test_retryable_error_keeps_partial_text(client, trip):
    err = anthropic.APIConnectionError(request=httpx.Request("POST", "http://x"))
    ev = chat(client, trip, "hi", ScriptedLLM([{"text": "Partial answer here", "raise": err}]), cid="e1")
    assert types(ev)[-1] == "error" and ev[-1]["retryable"] is True
    assert "done" not in types(ev)
    saved = client.get(f"/api/trips/{trip}/conversations/e1/messages").json()
    assert saved[-1]["role"] == "assistant" and saved[-1]["content"].startswith("Partial")


def test_missing_api_key_and_unknown_trip(client, trip, monkeypatch):
    from app import config

    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "")
    config.get_settings.cache_clear()
    client.app.state.llm = None
    with client.stream("POST", f"/api/trips/{trip}/chat", json={"message": "hi"}) as r:
        body = "".join(r.iter_lines())
    assert "GEMINI_API_KEY is not set" in body
    r = client.post("/api/trips/nope/chat", json={"message": "hi"})
    assert r.status_code == 404 and r.json()["error"]["code"] == "NOT_FOUND"
    assert client.post(f"/api/trips/{trip}/chat", json={"message": ""}).status_code == 422
