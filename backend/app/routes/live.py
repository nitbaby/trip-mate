from fastapi import APIRouter

from ..config import get_settings
from ..db import connect
from ..errors import not_found
from ..tools import cache, impl

router = APIRouter(prefix="/api/trips/{trip_id}", tags=["live"])


@router.get("/places")
def places(trip_id: str, lat: float | None = None, lng: float | None = None, q: str = "",
           location: str = "", vegetarian: bool = False, open_now: bool = False):
    with connect() as c:
        if not c.execute("SELECT 1 FROM trips WHERE id=?", (trip_id,)).fetchone():
            raise not_found("Trip")
    return impl.search_places(location or "tokyo", q, vegetarian, open_now, lat, lng, 2000, trip_id)


@router.get("/status")
def status(trip_id: str):
    """SET-01: health/mode of each integration with last time it was contacted."""
    s = get_settings()
    last = cache.last_contacted()
    mode = s.live_mode
    srcs = {"flight": "mock (no real provider configured)", "weather": "Open-Meteo", "places": "OpenStreetMap Nominatim",
            "fx": "Frankfurter"}
    return {"live_mode": mode, "anthropic_configured": bool(s.anthropic_api_key),
            "integrations": [{"name": k, "provider": srcs[k] if mode == "real" and k != "flight" else "mock",
                              "mode": "mock" if (mode == "mock" or k == "flight") else "real",
                              "last_contacted": last[k]} for k in srcs]}
