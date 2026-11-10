import json
import re

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field, field_validator
from sse_starlette.sse import EventSourceResponse

from ..agent.llm import build_llm, missing_key_message
from ..agent.loop import new_conversation_id, run_turn
from ..config import get_settings
from ..db import connect, row_to_dict
from ..errors import not_found

router = APIRouter(prefix="/api/trips/{trip_id}", tags=["chat"])


class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    conversationId: str | None = Field(default=None, min_length=1, max_length=64)
    preferences: dict[str, str] | None = None  # SET-02: units, currency, language

    @field_validator("preferences")
    @classmethod
    def _clean_prefs(cls, v):
        """Only known keys with tightly validated values reach the system prompt."""
        if not v:
            return None
        out = {}
        if v.get("units") in ("metric", "imperial"):
            out["units"] = v["units"]
        if re.fullmatch(r"[A-Z]{3}", v.get("currency", "")):
            out["currency"] = v["currency"]
        if re.fullmatch(r"[\w ()\-]{1,30}", v.get("language", "")):
            out["language"] = v["language"]
        return out or None


def _llm(request: Request):
    llm = getattr(request.app.state, "llm", None)
    if llm:
        return llm
    return build_llm(get_settings())


@router.post("/chat")
async def chat(trip_id: str, body: ChatIn, request: Request):
    with connect() as c:
        row = c.execute("SELECT * FROM trips WHERE id=?", (trip_id,)).fetchone()
        if not row:
            raise not_found("Trip")
        trip = row_to_dict(row, ("destinations",))
    cid = body.conversationId or new_conversation_id()
    llm = _llm(request)

    async def events():
        if llm is None:
            yield {"data": json.dumps({"type": "error", "code": "AGENT_FAILED", "retryable": False,
                                       "message": missing_key_message(get_settings())})}
            return
        async for ev in run_turn(trip=trip, conversation_id=cid, user_message=body.message, llm=llm,
                                 hub=request.app.state.hub, prefs=body.preferences):
            yield {"data": json.dumps(ev)}

    return EventSourceResponse(events(), headers={"X-Conversation-Id": cid})


@router.get("/conversations/{conversation_id}/messages")
def messages(trip_id: str, conversation_id: str, limit: int = 100):
    with connect() as c:
        rows = c.execute("""SELECT m.id, m.role, m.content, m.created_at FROM messages m
                            JOIN conversations v ON v.id = m.conversation_id
                            WHERE v.id=? AND v.trip_id=? ORDER BY m.rowid DESC LIMIT ?""",
                         (conversation_id, trip_id, max(1, min(limit, 200)))).fetchall()
        return [dict(r) for r in reversed(rows)]
