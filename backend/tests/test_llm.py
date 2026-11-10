import json

import httpx
import pytest
from app.agent.llm import (
    LLMError,
    OpenAICompatLLM,
    build_llm,
    sanitize_schema,
    to_openai_messages,
    to_openai_tools,
)
from app.config import Settings


def sse(*deltas, finish="stop"):
    """Build an OpenAI-style streaming body from a list of delta dicts."""
    out = []
    for i, d in enumerate(deltas):
        last = i == len(deltas) - 1
        out.append({"id": "c", "object": "chat.completion.chunk", "created": 0, "model": "m",
                    "choices": [{"index": 0, "delta": d, "finish_reason": finish if last else None}]})
    return "".join(f"data: {json.dumps(c)}\n\n" for c in out) + "data: [DONE]\n\n"


SLEPT: list[float] = []


async def fake_sleep(seconds):
    SLEPT.append(seconds)


def llm_with(handler, model="gemini-test", **kw):
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return OpenAICompatLLM("test-key", model, "http://mock.local/v1beta/openai/", http_client=client, provider_name="Gemini",
                           sleep=fake_sleep, **kw)


def stream_response(body):
    return httpx.Response(200, headers={"content-type": "text/event-stream"}, content=body.encode())


async def collect(llm, messages=None, tools=None):
    out = []
    async for kind, payload in llm.turn("sys", tools or [], messages or [{"role": "user", "content": "hi"}]):
        out.append((kind, payload))
    return out


def test_sanitize_schema_for_gemini():
    schema = {"title": "x", "type": "object", "additionalProperties": False, "properties": {
        "doc_type": {"anyOf": [{"type": "string"}, {"type": "null"}], "default": None, "title": "Doc Type"},
        "n": {"type": "integer", "default": 3}}, "required": ["n"]}
    out = sanitize_schema(schema)
    assert out == {"type": "object", "properties": {"doc_type": {"type": "string"}, "n": {"type": "integer"}},
                   "required": ["n"]}


def test_real_mcp_tool_schemas_are_gemini_safe():
    import asyncio

    from app.mcp_client import McpToolClient

    async def go():
        async with McpToolClient() as c:
            return await c.list_tools()

    tools = to_openai_tools(asyncio.run(go()))
    blob = json.dumps(tools)
    assert "anyOf" not in blob and '"title": "' not in blob and '"default"' not in blob  # (a *parameter* named title is fine)
    write = next(t for t in tools if t["function"]["name"] == "write_itinerary")
    assert "title" in write["function"]["parameters"]["properties"]
    assert {t["function"]["name"] for t in tools} >= {"search_docs", "write_itinerary"}


def test_message_translation_roundtrip():
    msgs = [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": [
            {"type": "text", "text": "checking"},
            {"type": "tool_use", "id": "t1", "name": "get_weather", "input": {"location": "Tokyo"},
             "extra_content": {"google": {"thought_signature": "sig"}}}]},
        {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t1", "content": '{"ok":1}'}]},
    ]
    out = to_openai_messages("SYS", msgs)
    assert [m["role"] for m in out] == ["system", "user", "assistant", "tool"]
    call = out[2]["tool_calls"][0]
    assert call["id"] == "t1" and json.loads(call["function"]["arguments"]) == {"location": "Tokyo"}
    assert call["extra_content"] == {"google": {"thought_signature": "sig"}}
    assert out[3] == {"role": "tool", "tool_call_id": "t1", "content": '{"ok":1}'}


async def test_streams_text():
    seen = {}

    def handler(req):
        seen["auth"], seen["url"], seen["body"] = req.headers["authorization"], str(req.url), json.loads(req.content)
        return stream_response(sse({"content": "Check-out "}, {"content": "is 11 AM [1]."}))

    out = await collect(llm_with(handler))
    assert [p for k, p in out if k == "text"] == ["Check-out ", "is 11 AM [1]."]
    final = out[-1][1]
    assert final["content"] == [{"type": "text", "text": "Check-out is 11 AM [1]."}] and final["stop_reason"] == "stop"
    assert seen["auth"] == "Bearer test-key" and seen["url"].endswith("/v1beta/openai/chat/completions")
    assert seen["body"]["model"] == "gemini-test" and seen["body"]["stream"] is True
    assert "reasoning_effort" not in seen["body"]  # only sent when configured
    assert seen["body"]["messages"][0] == {"role": "system", "content": "sys"}


async def test_streams_parallel_tool_calls_with_missing_ids_and_split_args():
    body = sse(
        {"tool_calls": [{"index": 0, "id": "a1", "type": "function", "function": {"name": "get_weather", "arguments": '{"loca'}}]},
        {"tool_calls": [{"index": 0, "function": {"arguments": 'tion": "Tokyo"}'}}]},
        # Gemini-style: second call has index 0 again and no id
        {"tool_calls": [{"index": 0, "function": {"name": "convert_currency",
                                                  "arguments": '{"amount": 5, "from_currency": "USD", "to_currency": "JPY"}'},
                         "extra_content": {"google": {"thought_signature": "s2"}}}]},
        finish="tool_calls")
    out = await collect(llm_with(lambda r: stream_response(body)))
    blocks = out[-1][1]["content"]
    assert out[-1][1]["stop_reason"] == "tool_use" and [b["name"] for b in blocks] == ["get_weather", "convert_currency"]
    assert blocks[0]["id"] == "a1" and blocks[0]["input"] == {"location": "Tokyo"}
    assert blocks[1]["id"].startswith("call_") and blocks[1]["input"]["amount"] == 5
    assert blocks[1]["extra_content"] == {"google": {"thought_signature": "s2"}}


async def test_bad_tool_arguments_become_empty_dict():
    body = sse({"tool_calls": [{"index": 0, "id": "z", "function": {"name": "get_weather", "arguments": "{oops"}}]},
               finish="tool_calls")
    out = await collect(llm_with(lambda r: stream_response(body)))
    assert out[-1][1]["content"][0]["input"] == {}


@pytest.mark.parametrize("status,retryable,fragment", [
    (401, False, "rejected the API key"), (403, False, "rejected the API key"),
    (404, False, "does not know the model"), (429, True, "rate limit"), (503, True, "problems"),
    (400, False, "rejected the request"), (402, False, "credits")])
async def test_error_mapping(status, retryable, fragment):
    llm = llm_with(lambda r: httpx.Response(status, json={"error": {"message": "x", "status": "E"}}))
    with pytest.raises(LLMError) as e:
        await collect(llm)
    assert e.value.retryable is retryable and fragment in e.value.message


def test_factory_selection():
    assert build_llm(Settings(_env_file=None, llm_provider="gemini")) is None
    g = build_llm(Settings(_env_file=None, llm_provider="gemini", gemini_api_key="k"))
    assert isinstance(g, OpenAICompatLLM) and g.model == "gemini-3.5-flash-lite" and g.reasoning_effort == "low"
    assert build_llm(Settings(_env_file=None, llm_provider="openai", llm_api_key="k")) is None  # needs model + url
    o = build_llm(Settings(_env_file=None, llm_provider="openai", llm_api_key="k", llm_model="m",
                           llm_base_url="https://api.groq.com/openai/v1"))
    assert isinstance(o, OpenAICompatLLM) and o.model == "m"
    assert Settings(_env_file=None).llm_provider == "gemini"  # Gemini is the default


def test_full_chat_turn_through_gemini_adapter_and_real_tools(client):
    """Mock Gemini asks for get_flight_status, then answers using the tool result."""
    from tests.test_agent import chat

    tid = client.post("/api/trips", json={"name": "T", "destinations": ["Tokyo"], "start_date": "2026-11-30",
                                          "end_date": "2026-12-06", "timezone": "Asia/Tokyo"}).json()["id"]
    requests = []

    def handler(req):
        body = json.loads(req.content)
        requests.append(body)
        if len(requests) == 1:
            return stream_response(sse({"content": "Let me check. "}, {"tool_calls": [
                {"index": 0, "id": "g1", "type": "function",
                 "function": {"name": "get_flight_status", "arguments": '{"flight_number":"JL44","date":"2026-11-30"}'}}]},
                finish="tool_calls"))
        tool_msg = next(m for m in body["messages"] if m["role"] == "tool")
        assert "delayed" in tool_msg["content"] and tool_msg["tool_call_id"] == "g1"
        return stream_response(sse({"content": "JL 44 is delayed by 35 minutes."}))

    ev = chat(client, tid, "Is my 6 PM flight delayed?", llm_with(handler))
    types = [e["type"] for e in ev]
    assert types[:3] == ["token", "tool_start", "tool_result"] and types[-1] == "done"
    assert next(e for e in ev if e["type"] == "tool_result")["summary"] == "JL44 delayed by 35 min"
    # tools sent to Gemini carry no trip_id and no unsupported schema keywords
    sent = json.dumps(requests[0]["tools"])
    assert "trip_id" not in sent and "anyOf" not in sent


def test_sanitize_keeps_a_parameter_named_title():
    from app.agent.llm import sanitize_schema
    out = sanitize_schema({"title": "Args", "type": "object", "required": ["title"],
                           "properties": {"title": {"title": "Title", "anyOf": [{"type": "string"}, {"type": "null"}], "default": None}}})
    assert out == {"type": "object", "required": ["title"], "properties": {"title": {"type": "string"}}}
