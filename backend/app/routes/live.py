from fastapi import APIRouter

from ..agent.llm import build_llm
from ..agent.ratelimit import quota_status, resolve_limits
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
    return {"live_mode": mode, "llm_provider": s.llm_provider, "llm_configured": build_llm(s) is not None,
            "llm_limits": _llm_limits(s),
            "integrations": [{"name": k, "provider": srcs[k] if (s.live_flights if k == "flight" else mode) == "real" else "mock",
                              "mode": s.live_flights if k == "flight" else mode,
                              "last_contacted": last[k]} for k in srcs]}


def _llm_limits(s) -> dict | None:
    lim = resolve_limits(s)
    if not lim:
        return None
    q = quota_status(s)
    return {"rpm": lim.rpm, "daily_limit": lim.daily, "requests_today": q["used"] if q else None, "model": lim.model_key}
