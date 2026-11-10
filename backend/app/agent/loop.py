"""Agent loop: one chat turn -> stream of typed ChatEvents (spec 5.2)."""
import json
import re
import uuid
from collections.abc import AsyncIterator

import anthropic

from ..config import get_settings
from ..db import connect, new_id, now_iso
from .guardrails import EXTERNAL_TOOLS, LABELS, summarize, verify_reason
from .llm import LLMError
from .prompt import system_prompt

MAX_ITERATIONS = 8
HISTORY_LIMIT = 20
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


async def run_turn(*, trip: dict, conversation_id: str, user_message: str, llm, hub) -> AsyncIterator[dict]:
    s = get_settings()
    conn = connect()
    saved_assistant = False
    full_text = ""
    try:
        history = _load_conversation(conn, trip["id"], conversation_id)
        _save(conn, conversation_id, "user", user_message)
        messages = [*history, {"role": "user", "content": user_message}]
        try:
            tools, with_trip = _model_tools(await hub.tools())
        except Exception:  # noqa: BLE001
            yield {"type": "error", "code": "AGENT_FAILED", "message": "The tool server is unavailable.", "retryable": True}
            return
        system = system_prompt(trip)
        refs: dict[int, dict] = {}
        conf_levels: list[str] = []
        wrote_itinerary = False
        tool_count = 0

        for _ in range(MAX_ITERATIONS):
            final = None
            async for kind, payload in llm.turn(system, tools, messages):
                if kind == "text":
                    full_text += payload
                    yield {"type": "token", "text": payload}
                else:
                    final = payload
            if final is None:
                raise RuntimeError("LLM returned no final message")
            messages.append({"role": "assistant", "content": final["content"]})
            tool_uses = [b for b in final["content"] if b["type"] == "tool_use"]
            if not tool_uses:
                break

            results = []
            for tu in tool_uses:
                name, args = tu["name"], dict(tu["input"] or {})
                yield {"type": "tool_start", "toolCallId": tu["id"], "name": name, "label": LABELS.get(name, name)}
                tool_count += 1
                if tool_count > s.max_tools_per_turn:
                    res = {"error": {"code": "BUDGET_EXCEEDED", "message": "Tool limit for this turn reached. Answer with what you have."}}
                elif name in EXTERNAL_TOOLS and _used_external(conn, conversation_id) >= s.max_external_calls_per_session:
                    res = {"error": {"code": "BUDGET_EXCEEDED", "message": "External lookup budget for this chat is used up."}}
                else:
                    if name in EXTERNAL_TOOLS:
                        _bump_external(conn, conversation_id)
                    if name in with_trip:
                        args["trip_id"] = trip["id"]
                    try:
                        res = await hub.call(name, args)
                    except Exception:  # noqa: BLE001
                        res = {"error": {"code": "EXTERNAL_UNAVAILABLE", "message": "Tool call failed."}}
                ok = "error" not in res
                if ok and name == "search_docs":
                    conf_levels.append(res["confidence"])
                    for h in res["results"]:
                        n = len(refs) + 1
                        refs[n] = {"docId": h["document_id"], "chunkId": h["chunk_id"],
                                   "label": f"{h['document_name']}, p.{h['page']}"}
                        h["ref"] = f"[{n}]"
                        for k in ("chunk_id", "document_id", "trip_id", "doc_type"):
                            h.pop(k, None)
                if ok and name == "write_itinerary":
                    wrote_itinerary = True
                    yield {"type": "itinerary_updated", "itemId": res["item_id"], "action": res["action"],
                           "undoId": res["undo_id"]}
                yield {"type": "tool_result", "toolCallId": tu["id"], "ok": ok, "summary": summarize(name, args, res)}
                results.append({"type": "tool_result", "tool_use_id": tu["id"], "content": json.dumps(res),
                                **({"is_error": True} if not ok else {})})
            messages.append({"role": "user", "content": results})
        else:
            full_text += "\n\n(I stopped because this took too many steps.)"
            yield {"type": "token", "text": "\n\n(I stopped because this took too many steps.)"}

        # citations: only markers the model actually used and that map to a real passage
        cited = []
        for m in re.findall(r"\[(\d+)\]", full_text):
            if int(m) in refs and m not in cited:
                cited.append(m)
        for m in cited:
            yield {"type": "citation", "marker": f"[{m}]", **refs[int(m)]}
        if conf_levels and not wrote_itinerary:  # actions skip the confidence check (spec 3.3)
            level = max(conf_levels, key=RANK.get)
            if level != "none" and not cited:
                level = "low"  # CHAT-02: no citation means no "high"
            yield {"type": "confidence", "level": level}
        reason = verify_reason(user_message, full_text)
        if reason:
            yield {"type": "verify", "reason": reason}
        mid = _save(conn, conversation_id, "assistant", full_text)
        saved_assistant = True
        yield {"type": "done", "messageId": mid}
    except (LLMError, anthropic.APIError, ValueError, RuntimeError) as e:
        if isinstance(e, LLMError):
            err = {"code": "AGENT_FAILED", "message": e.message, "retryable": e.retryable}
        elif isinstance(e, anthropic.APIError):
            err = _anthropic_error(e)
        else:
            err = {"code": "AGENT_FAILED", "message": str(e)[:160], "retryable": False}
        yield {"type": "error", **err}
    finally:
        if full_text and not saved_assistant:  # keep partial text on error / client stop (CHAT-06)
            try:
                _save(conn, conversation_id, "assistant", full_text)
            except Exception:  # noqa: BLE001
                pass
        conn.close()


def new_conversation_id() -> str:
    return uuid.uuid4().hex[:12]
