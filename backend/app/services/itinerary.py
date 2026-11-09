"""Itinerary logic shared by REST routes and agent/MCP tools."""
import json
from datetime import datetime

from ..db import new_id, now_iso
from ..errors import ApiError, not_found
from ..schemas import ItemIn, ItemPatch


def find_conflicts(items: list[dict]) -> dict[str, list[str]]:
    """ITIN-06: ids of items whose time ranges overlap (same start time also counts). Notes are ignored."""
    spans = []
    for i in items:
        if i["type"] == "note":
            continue
        s = datetime.fromisoformat(i["start_at"])
        e = datetime.fromisoformat(i["end_at"]) if i["end_at"] else s
        spans.append((i["id"], s, e))
    out: dict[str, list[str]] = {}
    for a in range(len(spans)):
        for b in range(a + 1, len(spans)):
            ia, sa, ea = spans[a]
            ib, sb, eb = spans[b]
            if sa == sb or (sa < eb and sb < ea):
                out.setdefault(ia, []).append(ib)
                out.setdefault(ib, []).append(ia)
    return out


def ensure_trip(c, trip_id):
    if not c.execute("SELECT 1 FROM trips WHERE id=?", (trip_id,)).fetchone():
        raise not_found("Trip")


def list_items(c, trip_id, date_from=None, date_to=None) -> list[dict]:
    ensure_trip(c, trip_id)
    q, args = "SELECT * FROM itinerary_items WHERE trip_id=?", [trip_id]
    if date_from:
        q += " AND start_at >= ?"
        args.append(date_from)
    if date_to:
        q += " AND start_at <= ?"
        args.append(date_to)
    items = [dict(r) for r in c.execute(q + " ORDER BY start_at", args)]
    conflicts = find_conflicts(items)
    for i in items:
        i["conflicts_with"] = conflicts.get(i["id"], [])
    return items


def get_item(c, trip_id, item_id) -> dict:
    r = c.execute("SELECT * FROM itinerary_items WHERE id=? AND trip_id=?", (item_id, trip_id)).fetchone()
    if not r:
        raise not_found("Itinerary item")
    return dict(r)


def create_item(c, trip_id, body: ItemIn) -> dict:
    ensure_trip(c, trip_id)
    iid = new_id()
    c.execute("INSERT INTO itinerary_items VALUES (?,?,?,?,?,?,?,?,?,?)",
              (iid, trip_id, body.type, body.title, body.start_at.isoformat(),
               body.end_at.isoformat() if body.end_at else None, body.location, body.notes,
               body.source, body.document_id))
    return get_item(c, trip_id, iid)


def update_item(c, trip_id, item_id, body: ItemPatch, source: str | None = None) -> dict:
    get_item(c, trip_id, item_id)
    fields = body.model_dump(exclude_unset=True)
    for k in ("start_at", "end_at"):
        if fields.get(k):
            fields[k] = fields[k].isoformat()
    if source:
        fields["source"] = source
    if fields:
        sets = ", ".join(f"{k}=?" for k in fields)
        c.execute(f"UPDATE itinerary_items SET {sets} WHERE id=?", (*fields.values(), item_id))
    return get_item(c, trip_id, item_id)


def delete_item(c, trip_id, item_id) -> dict:
    before = get_item(c, trip_id, item_id)
    c.execute("DELETE FROM itinerary_items WHERE id=?", (item_id,))
    return before


# ---- undo support for agent writes (ITIN-05) ----

def log_undo(c, trip_id, action, item_id, before: dict | None) -> str:
    uid = new_id()
    c.execute("INSERT INTO undo_log(id,trip_id,action,item_id,before,created_at) VALUES (?,?,?,?,?,?)",
              (uid, trip_id, action, item_id, json.dumps(before) if before else None, now_iso()))
    return uid


def undo(c, trip_id, undo_id) -> dict:
    r = c.execute("SELECT * FROM undo_log WHERE id=? AND trip_id=?", (undo_id, trip_id)).fetchone()
    if not r:
        raise not_found("Undo entry")
    if r["undone"]:
        raise ApiError("VALIDATION_FAILED", "Already undone", 409)
    before = json.loads(r["before"]) if r["before"] else None
    if r["action"] == "created":
        c.execute("DELETE FROM itinerary_items WHERE id=?", (r["item_id"],))
        result = {"undone": "created", "item_id": r["item_id"]}
    elif r["action"] == "updated":
        cols = [k for k in before if k != "id"]
        c.execute(f"UPDATE itinerary_items SET {', '.join(k + '=?' for k in cols)} WHERE id=?",
                  (*[before[k] for k in cols], r["item_id"]))
        result = {"undone": "updated", "item_id": r["item_id"]}
    else:  # deleted -> restore
        cols = list(before)
        c.execute(f"INSERT INTO itinerary_items({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
                  [before[k] for k in cols])
        result = {"undone": "deleted", "item_id": r["item_id"]}
    c.execute("UPDATE undo_log SET undone=1 WHERE id=?", (undo_id,))
    return result


def agent_write(c, trip_id, action: str, item_id: str | None, fields: dict) -> dict:
    """The single entry point for agent itinerary writes: marks source=agent and records an undo entry."""
    if action == "create":
        item = create_item(c, trip_id, ItemIn(**{**fields, "source": "agent"}))
        uid = log_undo(c, trip_id, "created", item["id"], None)
        res_action = "created"
    elif action == "update":
        if not item_id:
            raise ApiError("VALIDATION_FAILED", "item_id is required for update", 422)
        before = get_item(c, trip_id, item_id)
        item = update_item(c, trip_id, item_id, ItemPatch(**fields), source="agent")
        uid = log_undo(c, trip_id, "updated", item_id, before)
        res_action = "updated"
    elif action == "delete":
        if not item_id:
            raise ApiError("VALIDATION_FAILED", "item_id is required for delete", 422)
        item = delete_item(c, trip_id, item_id)
        uid = log_undo(c, trip_id, "deleted", item_id, item)
        res_action = "deleted"
    else:
        raise ApiError("VALIDATION_FAILED", "action must be create, update or delete", 422)
    c.commit()
    conflicts = []
    if res_action != "deleted":
        conflicts = next((i["conflicts_with"] for i in list_items(c, trip_id) if i["id"] == item["id"]), [])
    return {"action": res_action, "item_id": item["id"], "item": item, "undo_id": uid,
            "conflicts_with": conflicts}
