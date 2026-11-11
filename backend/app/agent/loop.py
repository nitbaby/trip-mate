"""Agent runtime: one chat turn -> stream of typed ChatEvents (spec 5.2).

Two modes share the same agent runner and guardrails:
  single: one agent with all tools (the original design)
  multi:  router -> specialist agents (parallel if more than one) -> composer -> citation verifier
"""
import asyncio
import json
import re
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass, field

import anthropic

from ..config import get_settings
from ..db import connect, new_id, now_iso
from .guardrails import EXTERNAL_TOOLS, LABELS, summarize, verify_reason
from .llm import LLMError
from .prompt import composer_prompt, role_prompt, system_prompt
from .ratelimit import quota_status
from .router import AGENTS, route
from .verify import verify_citations

MAX_ITERATIONS = 8
SPECIALIST_ITERATIONS = 5
HISTORY_LIMIT = 20
# an answer that says the itinerary was changed, checked against whether a write really succeeded
CHANGE_CLAIM = re.compile(r"\b(?:I(?:'ve|'ve| have)?\s+(?:added|scheduled|booked|removed|deleted|moved|updated|created)|"
                          r"(?:has|have) been (?:added|scheduled|booked|removed|deleted|moved|updated)|"
                          r"(?:added|scheduled|booked) (?:a |an |the )?\w*[^.\n]{0,40}(?:to|on|in) your (?:itinerary|schedule))", re.IGNORECASE)
RANK = {"none": 0, "low": 1, "high": 2}


def _model_tools(tools: list[dict]) -> tuple[list[dict], set[str]]:
    """Hide trip_id from the model (the backend injects it, so the model can't read another trip)."""
    out, with_trip = [], set()
    for t in tools:
        schema = json.loads(json.dumps(t["input_schema"]))
        if "trip_id" in schema.get("properties", {}):
            with_trip.add(t["name"])
            schema["properties"].pop("trip_id")
            schema["required"] = [r for r in schema.get("required", []) if r != "trip_id"]
        out.append({**t, "input_schema": schema})
    return out, with_trip


def _anthropic_error(e: Exception) -> dict:
    if isinstance(e, anthropic.AuthenticationError):
        return {"code": "AGENT_FAILED", "message": "The Anthropic API key was rejected. Check ANTHROPIC_API_KEY.", "retryable": False}
    if isinstance(e, anthropic.RateLimitError) or (isinstance(e, anthropic.APIStatusError) and e.status_code >= 500):
        return {"code": "AGENT_FAILED", "message": "The assistant is busy right now. Please retry.", "retryable": True}
    if isinstance(e, anthropic.APIConnectionError):
        return {"code": "AGENT_FAILED", "message": "Could not reach the assistant. Check your connection and retry.", "retryable": True}
    return {"code": "AGENT_FAILED", "message": "The assistant hit an unexpected error.", "retryable": True}


def _load_conversation(conn, trip_id: str, conversation_id: str) -> list[dict]:
    row = conn.execute("SELECT trip_id FROM conversations WHERE id=?", (conversation_id,)).fetchone()
    if row and row["trip_id"] != trip_id:
        raise ValueError("conversation belongs to another trip")
    if not row:
        conn.execute("INSERT INTO conversations VALUES (?,?,?)", (conversation_id, trip_id, now_iso()))
    rows = conn.execute("""SELECT role, content FROM messages WHERE conversation_id=?
                           ORDER BY rowid DESC LIMIT ?""", (conversation_id, HISTORY_LIMIT)).fetchall()
    return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]


def _save(conn, conversation_id, role, content) -> str:
    mid = new_id()
    conn.execute("INSERT INTO messages VALUES (?,?,?,?,?)", (mid, conversation_id, role, content, now_iso()))
    conn.commit()
    return mid


def _used_external(conn, cid) -> int:
    r = conn.execute("SELECT external_calls FROM usage WHERE conversation_id=?", (cid,)).fetchone()
    return r["external_calls"] if r else 0


def _bump_external(conn, cid):
    conn.execute("""INSERT INTO usage(conversation_id, external_calls) VALUES (?,1)
                    ON CONFLICT(conversation_id) DO UPDATE SET external_calls = external_calls + 1""", (cid,))
    conn.commit()


@dataclass
class Turn:
    """State shared by every agent in one chat turn. Budgets and citation numbering are turn-wide."""
    trip: dict
    conversation_id: str
    conn: object
    hub: object
    tools: list[dict]
    with_trip: set[str]
    prefs: dict | None = None
    refs: dict[int, dict] = field(default_factory=dict)       # [n] -> citation target + passage text (server side only)
    evidence: list[str] = field(default_factory=list)         # live tool results, used by the verifier
    conf_levels: list[str] = field(default_factory=list)
    tool_count: int = 0
    llm_calls: int = 0
    wrote_itinerary: bool = False
    failed_write: str = ""                                      # error text of a write_itinerary call that failed (and was not retried OK)
    streamed: str = ""                                          # everything streamed to the user as tokens


async def _none():
    return
    yield  # an empty async generator


async def run_agent(turn: Turn, llm, *, agent: str | None, system: str, allowed: set[str] | None, messages: list[dict],
                    stream_text: bool, out: dict, max_iter: int = MAX_ITERATIONS,
                    prefetch_docs: str | None = None, force_first_tool: str | None = None) -> AsyncIterator[dict]:
    """Run one agent to completion. Yields events; the agent's answer is left in out["text"]."""
    s = get_settings()
    tag = {"agent": agent} if agent else {}
    if agent:
        yield {"type": "agent_start", "agent": agent, "label": AGENTS[agent]["label"]}
    tools = [t for t in turn.tools if allowed is None or t["name"] in allowed]
    messages = list(messages)
    accumulated, last_text = "", ""
    exhausted = True
    for it in range(max_iter):
        final, last_text = None, ""
        if it == 0 and prefetch_docs and any(t["name"] == "search_docs" for t in tools):
            # Small models sometimes skip search_docs and answer from memory: search deterministically first.
            final = {"content": [{"type": "tool_use", "id": "prefetch_docs", "name": "search_docs",
                                  "input": {"query": prefetch_docs}, "synthetic": True}], "stop_reason": "tool_use"}
        else:
            turn.llm_calls += 1
        forced = {"force_tool": force_first_tool} if it == 0 and force_first_tool and any(t["name"] == force_first_tool for t in tools) else {}
        # the forced step offers only that tool: servers differ in how strictly they honour a named tool_choice
        call_tools = [_strict_create(t) for t in tools if t["name"] == force_first_tool] if forced else tools
        async for kind, payload in (_none() if final else llm.turn(system, call_tools, messages, **forced)):
            if kind == "wait":  # the adapter is queued for the rate limit or backing off: tell the UI
                yield {"type": "waiting", **payload, **tag}
            elif kind == "text":
                last_text += payload
                accumulated += payload
                if stream_text:
                    turn.streamed += payload
                    yield {"type": "token", "text": payload}
            else:
                final = payload
        if final is None:
            raise RuntimeError("LLM returned no final message")
        messages.append({"role": "assistant", "content": final["content"]})
        tool_uses = [b for b in final["content"] if b["type"] == "tool_use"]
        if not tool_uses:
            exhausted = False
            break

        results = []
        for tu in tool_uses:
            name, args = tu["name"], dict(tu["input"] or {})
            yield {"type": "tool_start", "toolCallId": tu["id"], "name": name, "label": LABELS.get(name, name), **tag}
            turn.tool_count += 1
            if allowed is not None and name not in allowed:
                res = {"error": {"code": "VALIDATION_FAILED", "message": "That tool is not available to you."}}
            elif turn.tool_count > s.max_tools_per_turn:
                res = {"error": {"code": "BUDGET_EXCEEDED", "message": "Tool limit for this turn reached. Answer with what you have."}}
            elif name in EXTERNAL_TOOLS and _used_external(turn.conn, turn.conversation_id) >= s.max_external_calls_per_session:
                res = {"error": {"code": "BUDGET_EXCEEDED", "message": "External lookup budget for this chat is used up."}}
            else:
                if name in EXTERNAL_TOOLS:
                    _bump_external(turn.conn, turn.conversation_id)
                if name in turn.with_trip:
                    args["trip_id"] = turn.trip["id"]
                try:
                    res = await turn.hub.call(name, args)
                except Exception:  # noqa: BLE001
                    res = {"error": {"code": "EXTERNAL_UNAVAILABLE", "message": "Tool call failed."}}
            ok = "error" not in res
            if ok and name == "search_docs":
                turn.conf_levels.append(res["confidence"])
                for h in res["results"]:
                    n = len(turn.refs) + 1
                    turn.refs[n] = {"docId": h["document_id"], "chunkId": h["chunk_id"],
                                    "label": f"{h['document_name']}, p.{h['page']}", "text": h["text"]}
                    h["ref"] = f"[{n}]"
                    for k in ("chunk_id", "document_id", "trip_id", "doc_type"):
                        h.pop(k, None)
            elif ok and name != "write_itinerary":
                turn.evidence.append(json.dumps(res))
            if name == "write_itinerary" and not ok:
                turn.failed_write = (res.get("error") or {}).get("message", "unknown error")
                res = {**res, "hint": "The itinerary was NOT changed. Call write_itinerary again with every required field "
                                      "(type, title, start_at), or tell the traveler the change failed. Never say it was added."}
            if ok and name == "write_itinerary":
                turn.failed_write = ""
                turn.wrote_itinerary = True
                yield {"type": "itinerary_updated", "itemId": res["item_id"], "action": res["action"], "undoId": res["undo_id"]}
            yield {"type": "tool_result", "toolCallId": tu["id"], "ok": ok, "summary": summarize(name, args, res), **tag}
            results.append({"type": "tool_result", "tool_use_id": tu["id"], "content": json.dumps(res),
                            **({"is_error": True} if not ok else {})})
        messages.append({"role": "user", "content": results})

    if exhausted:
        note = "\n\n(I stopped because this took too many steps.)"
        accumulated += note
        last_text += note
        if stream_text:
            turn.streamed += note
            yield {"type": "token", "text": note}
    out["text"] = accumulated if stream_text else last_text
    if agent:
        yield {"type": "agent_end", "agent": agent}


async def _merge(gens: list[AsyncIterator[dict]]) -> AsyncIterator[dict]:
    """Interleave several event streams (specialists running in parallel). A failure in any raises here."""
    q: asyncio.Queue = asyncio.Queue()
    end = object()

    async def pump(g):
        try:
            async for ev in g:
                await q.put(ev)
        except Exception as e:  # noqa: BLE001
            await q.put(e)
        finally:
            await q.put(end)

    tasks = [asyncio.create_task(pump(g)) for g in gens]
    left = len(tasks)
    try:
        while left:
            ev = await q.get()
            if ev is end:
                left -= 1
            elif isinstance(ev, Exception):
                raise ev
            else:
                yield ev
    finally:
        for t in tasks:
            t.cancel()


async def _answer_single(turn: Turn, llm, history: list[dict], user_message: str) -> AsyncIterator[dict]:
    out: dict = {}
    msgs = [*history, {"role": "user", "content": user_message}]
    async for ev in run_agent(turn, llm, agent=None, system=system_prompt(turn.trip, prefs=turn.prefs), allowed=None,
                              messages=msgs, stream_text=True, out=out, force_first_tool=_force(None, user_message)):
        yield ev


ADD_REQUEST = re.compile(r"^\W*(?:please |can you |could you )?(?:add|schedule|book|create|put)\b|"
                         r"\b(?:add|schedule|put)\b.{0,60}\b(?:to|on|in) (?:my |the )?(?:itinerary|schedule|plan)\b", re.IGNORECASE)


def _strict_create(tool: dict) -> dict:
    """The forced step is always an 'add': make the create fields required in the schema the model sees, because
    small models treat the optional-looking title as skippable and put the name in notes."""
    schema = json.loads(json.dumps(tool["input_schema"]))
    schema["required"] = ["action", "type", "title", "start_at"]
    props = schema.get("properties", {})
    if "action" in props:
        props["action"] = {"type": "string", "enum": ["create"]}
    if "title" in props:
        props["title"] = {"type": "string", "description": 'Short name of the item, e.g. "Dinner"'}
    if "type" in props:
        props["type"] = {"type": "string", "enum": ["flight", "hotel", "reservation", "activity", "transit", "note"]}
    if "start_at" in props:
        props["start_at"] = {"type": "string", "description": "ISO 8601 local time, e.g. 2026-12-02T20:00:00"}
    return {**tool, "input_schema": schema}


def _force(agent: str | None, message: str) -> str | None:
    """Small models sometimes say they added something without calling the tool: an explicit 'add ...' request
    forces the first step to be write_itinerary (the model still fills in the arguments)."""
    return "write_itinerary" if agent in (None, "itinerary") and ADD_REQUEST.search(message) else None


def _prefetch(agent: str, message: str) -> str | None:
    """Questions about the traveler's own documents always get a search first; live questions about 'my ...' too."""
    if agent == "docs" or (agent == "live" and re.search(r"\bmy\b", message, re.IGNORECASE)):
        return message
    return None


async def _answer_multi(turn: Turn, llm, history: list[dict], user_message: str) -> AsyncIterator[dict]:
    intents = route(user_message)
    msgs = [*history, {"role": "user", "content": user_message}]
    if len(intents) == 1:  # the specialist answers the user directly: no extra composer call
        a = intents[0]
        async for ev in run_agent(turn, llm, agent=a, system=role_prompt(a, turn.trip, prefs=turn.prefs),
                                  allowed=AGENTS[a]["tools"], messages=msgs, stream_text=True, out={},
                                  prefetch_docs=_prefetch(a, user_message), force_first_tool=_force(a, user_message)):
            yield ev
        return
    outs: dict[str, dict] = {a: {} for a in intents}
    gens = [run_agent(turn, llm, agent=a, system=role_prompt(a, turn.trip, prefs=turn.prefs), allowed=AGENTS[a]["tools"],
                      messages=msgs, stream_text=False, out=outs[a], max_iter=SPECIALIST_ITERATIONS,
                      prefetch_docs=_prefetch(a, user_message), force_first_tool=_force(a, user_message)) for a in intents]
    async for ev in _merge(gens):
        yield ev
    findings = "\n\n".join(f"[{AGENTS[a]['label']}]\n{outs[a].get('text', '').strip() or '(no answer)'}" for a in intents)
    yield {"type": "agent_start", "agent": "composer", "label": "Composing the answer"}
    turn.llm_calls += 1
    final = None
    async for kind, payload in llm.turn(composer_prompt(turn.trip, turn.prefs), [],
                                        [{"role": "user", "content": f"Question: {user_message}\n\nSpecialist answers:\n\n{findings}"}]):
        if kind == "wait":
            yield {"type": "waiting", **payload, "agent": "composer"}
        elif kind == "text":
            turn.streamed += payload
            yield {"type": "token", "text": payload}
        else:
            final = payload
    if final is None:
        raise RuntimeError("LLM returned no final message")
    yield {"type": "agent_end", "agent": "composer"}


async def run_turn(*, trip: dict, conversation_id: str, user_message: str, llm, hub, prefs: dict | None = None,
                   mode: str | None = None) -> AsyncIterator[dict]:
    s = get_settings()
    mode = mode if mode in ("single", "multi") else s.agent_mode
    conn = connect()
    saved_assistant = False
    turn = None
    try:
        history = _load_conversation(conn, trip["id"], conversation_id)
        _save(conn, conversation_id, "user", user_message)
        try:
            tools, with_trip = _model_tools(await hub.tools())
        except Exception:  # noqa: BLE001
            yield {"type": "error", "code": "AGENT_FAILED", "message": "The tool server is unavailable.", "retryable": True}
            return
        turn = Turn(trip=trip, conversation_id=conversation_id, conn=conn, hub=hub, tools=tools, with_trip=with_trip, prefs=prefs)
        answer = _answer_multi if mode == "multi" else _answer_single
        async for ev in answer(turn, llm, history, user_message):
            yield ev
        claims_change = bool(CHANGE_CLAIM.search(turn.streamed))
        if not turn.wrote_itinerary and (turn.failed_write or claims_change):
            note = ("\n\n⚠️ The itinerary was NOT changed: the update failed. Please try again with the day, time and a title."
                    if turn.failed_write else
                    "\n\n⚠️ The itinerary was NOT changed: no update was made. Please try again.")
            turn.streamed += note
            yield {"type": "token", "text": note}
        full_text = turn.streamed

        # citations: only markers the model used that map to a real passage (and, in multi mode, are grounded)
        cited = []
        for m in re.findall(r"\[(\d+)\]", full_text):
            if int(m) in turn.refs and m not in cited:
                cited.append(m)
        supported = cited
        if mode == "multi":
            grounded = verify_citations(full_text, turn.refs, turn.evidence)
            supported = [m for m in cited if grounded.get(m, False)]
            if cited:
                yield {"type": "verified", "checked": len(cited), "unsupported": len(cited) - len(supported)}
        for m in supported:
            r = turn.refs[int(m)]
            yield {"type": "citation", "marker": f"[{m}]", "docId": r["docId"], "chunkId": r["chunkId"], "label": r["label"]}
        if turn.conf_levels and not turn.wrote_itinerary:  # actions skip the confidence check (spec 3.3)
            level = max(turn.conf_levels, key=RANK.get)
            if level != "none" and not supported:
                level = "low"  # CHAT-02: no (grounded) citation means no "high"
            yield {"type": "confidence", "level": level}
        reason = verify_reason(user_message, full_text)
        if reason:
            yield {"type": "verify", "reason": reason}
        mid = _save(conn, conversation_id, "assistant", full_text)
        saved_assistant = True
        done = {"type": "done", "messageId": mid, "agentMode": mode, "llmCalls": turn.llm_calls, "toolCalls": turn.tool_count}
        try:
            quota = quota_status(s)
        except Exception:  # noqa: BLE001 - a quota read must never break an answer
            quota = None
        if quota:
            done["quota"] = {"used": quota["used"], "limit": quota["limit"]}
        yield done
    except (LLMError, anthropic.APIError, ValueError, RuntimeError) as e:
        if isinstance(e, LLMError):
            err = {"code": "AGENT_FAILED", "message": e.message, "retryable": e.retryable}
        elif isinstance(e, anthropic.APIError):
            err = _anthropic_error(e)
        else:
            err = {"code": "AGENT_FAILED", "message": str(e)[:160], "retryable": False}
        yield {"type": "error", **err}
    finally:
        text = turn.streamed if turn else ""
        if text and not saved_assistant:  # keep partial text on error / client stop (CHAT-06)
            try:
                _save(conn, conversation_id, "assistant", text)
            except Exception:  # noqa: BLE001
                pass
        conn.close()


def new_conversation_id() -> str:
    return uuid.uuid4().hex[:12]
