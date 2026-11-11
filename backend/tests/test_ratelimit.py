import json

import httpx
import pytest
from app.agent.llm import LLMError
from app.agent.ratelimit import (
    Limits,
    RateLimiter,
    TooLong,
    count_request,
    is_daily_exhausted,
    limiter_for,
    quota_status,
    resolve_limits,
    retry_after_seconds,
    used_today,
)
from app.config import Settings

from tests.test_llm import SLEPT, collect, llm_with, sse, stream_response


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


# ---------- the sliding-window limiter ----------
def test_window_allows_rpm_then_queues_in_order():
    clk = Clock()
    rl = RateLimiter(3, clock=clk)
    assert [rl.reserve(100) for _ in range(3)] == [0, 0, 0]
    clk.t += 10
    assert rl.reserve(100) == pytest.approx(50)   # 4th waits for the first slot to leave the window (t+60)
    assert rl.reserve(100) == pytest.approx(50)   # 5th shares that slot
    assert rl.reserve(100) == pytest.approx(50)   # 6th shares the same slot (3 per window is allowed)
    clk.t += 60   # now 1070: the original three left the window, but the three reserved for 1060 are still in it
    assert rl.reserve(100) == pytest.approx(50)    # so the 7th must wait until 1120
    clk.t += 60   # now 1130: everything but the 1120 reservation has aged out
    assert rl.reserve(100) == 0


def test_window_refuses_waits_longer_than_max_and_claims_nothing():
    clk = Clock()
    rl = RateLimiter(1, clock=clk)
    rl.reserve(100)
    with pytest.raises(TooLong) as e:
        rl.reserve(30)
    assert e.value.seconds == pytest.approx(60)
    assert len(rl.stamps) == 1
    clk.t += 61
    assert rl.reserve(30) == 0


def test_limiter_is_shared_per_model_across_adapters():
    assert limiter_for("gemini:m", 12) is limiter_for("gemini:m", 12)
    assert limiter_for("gemini:m", 12) is not limiter_for("gemini:other", 12)


# ---------- limits resolution ----------
def test_resolve_limits_defaults_and_overrides():
    g = resolve_limits(Settings(_env_file=None, llm_provider="gemini", gemini_model="gemini-3.5-flash-lite"))
    assert (g.rpm, g.daily, g.model_key) == (12, 500, "gemini:gemini-3.5-flash-lite")
    assert resolve_limits(Settings(_env_file=None, llm_provider="openai", llm_model="qwen")) is None        # local: unlimited
    assert resolve_limits(Settings(_env_file=None, llm_provider="demo")) is None
    o = resolve_limits(Settings(_env_file=None, llm_provider="gemini", llm_max_rpm=5, llm_daily_limit=0))
    assert (o.rpm, o.daily) == (5, 0)
    assert resolve_limits(Settings(_env_file=None, llm_provider="gemini", llm_max_rpm=0, llm_daily_limit=0)) is None
    r = resolve_limits(Settings(_env_file=None, llm_provider="openai", llm_model="m", llm_max_rpm=20))
    assert (r.rpm, r.daily) == (20, 0)


def test_parse_provider_retry_hints():
    assert retry_after_seconds({"retry-after": "7"}, "") == 7
    body = json.dumps([{"error": {"code": 429, "details": [{"@type": "x.RetryInfo", "retryDelay": "23s"}]}}])
    assert retry_after_seconds({}, body) == 23
    assert retry_after_seconds({}, "Please retry in 4.5s.") == 4.5
    assert retry_after_seconds({}, "nothing") is None
    assert is_daily_exhausted('{"quotaId": "GenerateRequestsPerDayPerProjectPerModel-FreeTier"}')
    assert not is_daily_exhausted('{"quotaId": "GenerateRequestsPerMinutePerProjectPerModel-FreeTier"}')


# ---------- the adapter: queueing, 429 handling, retries, daily budget ----------
async def test_adapter_waits_for_a_free_slot_and_tells_the_caller(client):
    lim = Limits(rpm=2, daily=0, tz="UTC", max_wait=100.0, model_key="gemini:t-queue")
    SLEPT.clear()
    llm = llm_with(lambda r: stream_response(sse({"content": "ok"})), limits=lim)
    first, second, third = await collect(llm), await collect(llm), await collect(llm)
    assert not any(k == "wait" for k, _ in first + second)
    waits = [p for k, p in third if k == "wait"]
    assert waits and waits[0]["reason"] == "rate_limit" and 50 <= waits[0]["seconds"] <= 61
    assert SLEPT and SLEPT[-1] > 50 and third[-1][0] == "final"


async def test_adapter_fails_fast_when_the_wait_is_too_long(client):
    lim = Limits(rpm=1, daily=0, tz="UTC", max_wait=10.0, model_key="gemini:t-toolong")
    llm = llm_with(lambda r: stream_response(sse({"content": "ok"})), limits=lim)
    await collect(llm)
    with pytest.raises(LLMError) as e:
        await collect(llm)
    assert e.value.retryable and "Try again in about" in e.value.message


async def test_429_honours_retry_delay_then_succeeds():
    calls = []

    def handler(req):
        calls.append(1)
        if len(calls) == 1:
            return httpx.Response(429, headers={"retry-after": "3"}, json={"error": {"message": "slow down"}})
        return stream_response(sse({"content": "done"}))

    SLEPT.clear()
    out = await collect(llm_with(handler))
    assert [p for k, p in out if k == "wait"] == [{"seconds": 4, "reason": "retry"}]
    assert SLEPT == [4.0] and len(calls) == 2
    assert [p for k, p in out if k == "text"] == ["done"]


async def test_429_with_a_long_delay_is_not_retried():
    llm = llm_with(lambda r: httpx.Response(429, headers={"retry-after": "120"}, json={"error": {"message": "x"}}),
                   limits=Limits(rpm=0, daily=0, tz="UTC", max_wait=45.0, model_key="gemini:t-long"))
    with pytest.raises(LLMError) as e:
        await collect(llm)
    assert e.value.retryable and "120" in e.value.message


async def test_daily_429_is_final_and_explains_the_reset():
    body = {"error": {"message": "quota", "details": [{"quotaId": "GenerateRequestsPerDayPerProjectPerModel-FreeTier"}]}}
    calls = []
    llm = llm_with(lambda r: (calls.append(1), httpx.Response(429, json=body))[1])
    with pytest.raises(LLMError) as e:
        await collect(llm)
    assert not e.value.retryable and "midnight Pacific" in e.value.message and len(calls) == 1


async def test_persistent_429_gives_up_after_two_retries():
    calls = []
    llm = llm_with(lambda r: (calls.append(1), httpx.Response(429, json={"error": {"message": "x"}}))[1])
    with pytest.raises(LLMError):
        await collect(llm)
    assert len(calls) == 3


async def test_503_is_retried_once_and_midstream_failure_is_not():
    n = []

    def handler(req):
        n.append(1)
        return httpx.Response(503, json={"error": {"message": "busy"}}) if len(n) == 1 else stream_response(sse({"content": "hi"}))

    assert [p for k, p in await collect(llm_with(handler)) if k == "text"] == ["hi"]

    class Broken(httpx.AsyncByteStream):  # sends one chunk, then the connection dies
        async def __aiter__(self):
            yield ('data: ' + json.dumps({"id": "c", "object": "chat.completion.chunk", "created": 0, "model": "m", "choices": [
                {"index": 0, "delta": {"content": "par"}, "finish_reason": None}]}) + "\n\n").encode()
            raise httpx.ReadError("connection reset")

    m = []

    def dying(req):
        m.append(1)
        return httpx.Response(200, headers={"content-type": "text/event-stream"}, stream=Broken())

    with pytest.raises(LLMError):
        await collect(llm_with(dying))
    assert len(m) == 1  # output had started, so no retry (it would duplicate text)


async def test_daily_budget_counts_requests_and_blocks_at_the_limit(client):
    lim = Limits(rpm=0, daily=3, tz="UTC", max_wait=10.0, model_key="gemini:t-daily")
    llm = llm_with(lambda r: stream_response(sse({"content": "ok"})), limits=lim)
    for _ in range(3):
        await collect(llm)
    assert used_today(lim) == 3
    with pytest.raises(LLMError) as e:
        await collect(llm)
    assert not e.value.retryable and "daily limit of 3" in e.value.message
    assert used_today(lim) == 3  # the blocked attempt is not counted
    count_request(lim)
    assert used_today(lim) == 4


def test_status_endpoint_and_done_event_report_quota(client, monkeypatch):
    from app import config

    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    monkeypatch.setenv("GEMINI_MODEL", "gemini-t-status")
    config.get_settings.cache_clear()
    tid = client.post("/api/trips", json={"name": "T", "destinations": ["X"], "start_date": "2026-01-01", "end_date": "2026-01-02"}).json()["id"]
    lim = resolve_limits(config.get_settings())
    for _ in range(5):
        count_request(lim)
    st = client.get(f"/api/trips/{tid}/status").json()
    assert st["llm_limits"] == {"rpm": 12, "daily_limit": 500, "requests_today": 5, "model": "gemini:gemini-t-status"}
    assert quota_status(config.get_settings())["used"] == 5


def test_chat_stream_carries_waiting_events_and_quota(client, monkeypatch):
    from app import config

    from tests.test_agent import chat

    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    monkeypatch.setenv("GEMINI_MODEL", "gemini-t-chat")
    config.get_settings.cache_clear()
    tid = client.post("/api/trips", json={"name": "T", "destinations": ["X"], "start_date": "2026-01-01", "end_date": "2026-01-02"}).json()["id"]

    class WaitingLLM:
        async def turn(self, system, tools, messages):
            yield "wait", {"seconds": 8, "reason": "rate_limit"}
            yield "text", "hello"
            yield "final", {"content": [{"type": "text", "text": "hello"}], "stop_reason": "end_turn"}

    ev = chat(client, tid, "hi", WaitingLLM())
    w = next(e for e in ev if e["type"] == "waiting")
    assert w["seconds"] == 8 and w["reason"] == "rate_limit"
    assert [e["type"] for e in ev].index("waiting") < [e["type"] for e in ev].index("token")
    assert ev[-1]["type"] == "done" and ev[-1]["quota"] == {"used": 0, "limit": 500}
