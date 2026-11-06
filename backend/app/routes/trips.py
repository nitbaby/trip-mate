import json

from fastapi import APIRouter

from ..db import connect, new_id, now_iso, row_to_dict
from ..errors import not_found
from ..ingest.facts import public_facts
from ..schemas import TripIn

router = APIRouter(prefix="/api/trips", tags=["trips"])


def _trip(row):
    d = dict(row)
    d["destinations"] = json.loads(d["destinations"])
    return d


@router.get("")
def list_trips():
    with connect() as c:
        return [_trip(r) for r in c.execute("SELECT * FROM trips ORDER BY start_date")]


@router.post("", status_code=201)
def create_trip(body: TripIn):
    tid = new_id()
    with connect() as c:
        c.execute("INSERT INTO trips VALUES (?,?,?,?,?,?,?)",
                  (tid, body.name, json.dumps(body.destinations), str(body.start_date),
                   str(body.end_date), body.timezone, now_iso()))
        return _trip(c.execute("SELECT * FROM trips WHERE id=?", (tid,)).fetchone())


@router.get("/{trip_id}")
def get_trip(trip_id: str):
    with connect() as c:
        t = c.execute("SELECT * FROM trips WHERE id=?", (trip_id,)).fetchone()
        if not t:
            raise not_found("Trip")
        out = _trip(t)
        out["itinerary"] = [dict(r) for r in c.execute(
            "SELECT * FROM itinerary_items WHERE trip_id=? ORDER BY start_at", (trip_id,))]
        docs = []
        for r in c.execute("SELECT * FROM documents WHERE trip_id=? ORDER BY uploaded_at", (trip_id,)):
            d = row_to_dict(r, ("key_facts",))
            d["key_facts"] = public_facts(d["key_facts"])
            docs.append(d)
        out["documents"] = docs
        return out
