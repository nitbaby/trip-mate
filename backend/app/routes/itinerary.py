from datetime import datetime

from fastapi import APIRouter

from ..db import connect, new_id
from ..errors import not_found
from ..schemas import ItemIn, ItemPatch

router = APIRouter(prefix="/api/trips/{trip_id}/itinerary", tags=["itinerary"])


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


def _ensure_trip(c, trip_id):
    if not c.execute("SELECT 1 FROM trips WHERE id=?", (trip_id,)).fetchone():
        raise not_found("Trip")


@router.get("")
def list_items(trip_id: str, date_from: str | None = None, date_to: str | None = None):
    with connect() as c:
        _ensure_trip(c, trip_id)
        q, args = "SELECT * FROM itinerary_items WHERE trip_id=?", [trip_id]
        if date_from:
            q += " AND start_at >= ?"; args.append(date_from)
        if date_to:
            q += " AND start_at <= ?"; args.append(date_to)
        items = [dict(r) for r in c.execute(q + " ORDER BY start_at", args)]
    conflicts = find_conflicts(items)
    for i in items:
        i["conflicts_with"] = conflicts.get(i["id"], [])
    return items


@router.post("", status_code=201)
def create_item(trip_id: str, body: ItemIn):
    iid = new_id()
    with connect() as c:
        _ensure_trip(c, trip_id)
        c.execute("INSERT INTO itinerary_items VALUES (?,?,?,?,?,?,?,?,?,?)",
                  (iid, trip_id, body.type, body.title, body.start_at.isoformat(),
                   body.end_at.isoformat() if body.end_at else None, body.location, body.notes,
                   body.source, body.document_id))
        return dict(c.execute("SELECT * FROM itinerary_items WHERE id=?", (iid,)).fetchone())


@router.patch("/{item_id}")
def update_item(trip_id: str, item_id: str, body: ItemPatch):
    fields = body.model_dump(exclude_unset=True)
    for k in ("start_at", "end_at"):
        if fields.get(k):
            fields[k] = fields[k].isoformat()
    with connect() as c:
        if not c.execute("SELECT 1 FROM itinerary_items WHERE id=? AND trip_id=?", (item_id, trip_id)).fetchone():
            raise not_found("Itinerary item")
        if fields:
            sets = ", ".join(f"{k}=?" for k in fields)
            c.execute(f"UPDATE itinerary_items SET {sets} WHERE id=?", (*fields.values(), item_id))
        return dict(c.execute("SELECT * FROM itinerary_items WHERE id=?", (item_id,)).fetchone())


@router.delete("/{item_id}", status_code=204)
def delete_item(trip_id: str, item_id: str):
    with connect() as c:
        cur = c.execute("DELETE FROM itinerary_items WHERE id=? AND trip_id=?", (item_id, trip_id))
        if cur.rowcount == 0:
            raise not_found("Itinerary item")
