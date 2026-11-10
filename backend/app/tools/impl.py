"""Tool implementations. Used by the MCP server (and tests). Every tool returns plain JSON-able dicts."""
from .. import vectors
from ..confidence import assess
from ..db import connect
from ..errors import not_found
from ..ingest.mask import redact
from ..services import itinerary as itin
from . import flights, fx, places, weather


def search_docs(trip_id: str, query: str, doc_type: str | None = None, k: int = 5) -> dict:
    with connect() as c:
        if not c.execute("SELECT 1 FROM trips WHERE id=?", (trip_id,)).fetchone():
            raise not_found("Trip")  # an unknown trip must not look like "no matching documents"
    hits = vectors.query(trip_id, query, k=max(1, min(k, 10)), doc_type=doc_type)
    best = hits[0]["score"] if hits else None
    confidence, hits = assess(hits)
    with connect() as c:
        for h in hits:
            r = c.execute("""SELECT ch.page, d.filename FROM chunks ch JOIN documents d ON d.id=ch.document_id
                             WHERE ch.id=?""", (h["chunk_id"],)).fetchone()
            h["page"], h["document_name"] = (r["page"], r["filename"]) if r else (None, None)
            h["text"] = redact(h["text"])  # sensitive values never reach the model (spec 8: redact before cloud)
    return {"query": query, "confidence": confidence, "results": hits,
            "closest_score": best if confidence == "none" else None}


def read_itinerary(trip_id: str, date_from: str | None = None, date_to: str | None = None) -> dict:
    with connect() as c:
        return {"items": itin.list_items(c, trip_id, date_from, date_to)}


def write_itinerary(trip_id: str, action: str, item_id: str | None = None, type: str | None = None,
                    title: str | None = None, start_at: str | None = None, end_at: str | None = None,
                    location: str | None = None, notes: str | None = None) -> dict:
    fields = {k: v for k, v in {"type": type, "title": title, "start_at": start_at, "end_at": end_at,
                                    "location": location, "notes": notes}.items() if v is not None}
    with connect() as c:
        return itin.agent_write(c, trip_id, action, item_id, fields)


def trip_timezone(trip_id: str | None) -> str:
    if not trip_id:
        return "UTC"
    with connect() as c:
        r = c.execute("SELECT timezone FROM trips WHERE id=?", (trip_id,)).fetchone()
        if not r:
            raise not_found("Trip")
        return r["timezone"]


def search_places(location: str, query: str = "", vegetarian: bool = False, open_now: bool = False,
                  lat: float | None = None, lng: float | None = None, radius_m: int = 2000,
                  trip_id: str | None = None) -> dict:
    return places.search_places(location, query, vegetarian, lat, lng, radius_m, open_now, trip_timezone(trip_id))


get_flight_status = flights.get_flight_status
get_weather = weather.get_weather
convert_currency = fx.convert_currency
