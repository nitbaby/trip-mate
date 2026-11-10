"""Places search with rating, open-now, distance and a vegetarian filter (LIVE-03)."""
import math
from datetime import datetime
from zoneinfo import ZoneInfo

import httpx

from ..config import get_settings
from .cache import TTL, cached

# Known anchor points for mock mode (sample data, approximate).
ANCHORS = {"tokyo": (35.6762, 139.6503), "shinjuku": (35.6938, 139.7034), "shinjuku granbell hotel": (35.6954, 139.7040),
           "shibuya": (35.6580, 139.7016)}

# name, lat, lng, rating, cuisine, vegetarian, hours "HH:MM-HH:MM" (close may be past midnight, e.g. 18:00-26:00)
MOCK_PLACES = [
    ("Ain Soph. Journey Shinjuku", 35.6911, 139.7044, 4.5, "vegan cafe", True, "11:00-22:00"),
    ("Falafel Garden Shinjuku", 35.6942, 139.7002, 4.2, "middle eastern", True, "07:00-23:00"),
    ("T's TanTan Tokyo Station", 35.6812, 139.7671, 4.4, "vegan ramen", True, "08:00-22:30"),
    ("Mominoki House", 35.6694, 139.7058, 4.3, "organic vegetarian", True, "11:30-21:00"),
    ("Kabukicho 24h Ramen", 35.6955, 139.7035, 3.9, "ramen", False, "00:00-24:00"),
    ("Omoide Yokocho Yakitori", 35.6928, 139.6996, 4.1, "yakitori", False, "17:00-26:00"),
    ("Daigo Shojin Ryori", 35.6586, 139.7454, 4.6, "shojin ryori", True, "11:30-14:00"),
]


def haversine_m(a: tuple[float, float], b: tuple[float, float]) -> int:
    la1, lo1, la2, lo2 = map(math.radians, (*a, *b))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return round(2 * 6371000 * math.asin(math.sqrt(h)))


def is_open(hours: str | None, now: datetime) -> bool | None:
    if not hours:
        return None
    o, c = hours.split("-")
    om = int(o[:2]) * 60 + int(o[3:])
    cm = int(c[:2]) * 60 + int(c[3:])
    m = now.hour * 60 + now.minute
    return om <= m < cm or om <= m + 1440 < cm  # second clause handles past-midnight closing


def resolve_origin(location: str, lat: float | None, lng: float | None) -> tuple[float, float]:
    if lat is not None and lng is not None:
        return lat, lng
    key = location.lower().strip()
    if key in ANCHORS:
        return ANCHORS[key]
    for k, v in ANCHORS.items():
        if k in key:
            return v
    if get_settings().live_mode == "real":
        with httpx.Client(timeout=10, headers={"User-Agent": "TripMate-dev"}) as h:
            r = h.get("https://nominatim.openstreetmap.org/search", params={"q": location, "format": "json", "limit": 1}).json()
        if r:
            return float(r[0]["lat"]), float(r[0]["lon"])
    raise ValueError(f"Could not locate '{location}'. Provide lat/lng or a known place.")


GENERIC = {"restaurant", "restaurants", "food", "place", "places", "near", "nearby", "vegetarian", "vegan",
           "eat", "dinner", "lunch", "breakfast", "open", "good", "best", "cafe", "the", "a", "in", "to", "for"}


def _mock(origin, query, vegetarian, radius_m):
    # drop generic words: "vegetarian restaurant" must not filter names/cuisines literally
    q = " ".join(w for w in (query or "").lower().split() if w not in GENERIC)
    out = []
    for name, la, lo, rating, cuisine, veg, hours in MOCK_PLACES:
        d = haversine_m(origin, (la, lo))
        if d > radius_m or (vegetarian and not veg):
            continue
        if q and not any(w in f"{name} {cuisine}".lower() for w in q.split()):
            continue
        out.append({"name": name, "lat": la, "lng": lo, "rating": rating, "cuisine": cuisine,
                    "vegetarian_friendly": veg, "hours": hours, "distance_m": d})
    return out


def _real(origin, query, vegetarian, radius_m):
    # Nominatim can't filter by diet, so "vegetarian" is not sent; results are flagged unknown for diet.
    term = (query or "restaurant").replace("vegetarian", "").strip() or "restaurant"
    d = radius_m / 111000
    box = f"{origin[1]-d},{origin[0]+d},{origin[1]+d},{origin[0]-d}"
    with httpx.Client(timeout=12, headers={"User-Agent": "TripMate-dev"}) as h:
        res = h.get("https://nominatim.openstreetmap.org/search", params={
            "q": term, "format": "json", "limit": 10, "viewbox": box, "bounded": 1}).json()
    return [{"name": r["display_name"].split(",")[0], "lat": float(r["lat"]), "lng": float(r["lon"]), "rating": None,
             "cuisine": r.get("type"), "vegetarian_friendly": None, "hours": None,
             "distance_m": haversine_m(origin, (float(r["lat"]), float(r["lon"])))} for r in res]


def search_places(location: str, query: str = "", vegetarian: bool = False, lat: float | None = None,
                  lng: float | None = None, radius_m: int = 2000, open_now: bool = False,
                  tz: str = "Asia/Tokyo", now: datetime | None = None) -> dict:
    origin = resolve_origin(location, lat, lng)
    mode = get_settings().live_mode
    key = f"places:{mode}:{origin[0]:.3f},{origin[1]:.3f}:{query}:{vegetarian}:{radius_m}"
    c = cached(key, TTL["places"], lambda: {"results": (_real if mode == "real" else _mock)(origin, query, vegetarian, radius_m),
                                            "source": "nominatim" if mode == "real" else "mock"})
    now = now or datetime.now(ZoneInfo(tz))
    results = []
    for p in c["results"]:  # open-now is evaluated at call time, never cached
        p = {**p, "open_now": is_open(p.get("hours"), now)}
        if open_now and p["open_now"] is False:
            continue
        results.append(p)
    results.sort(key=lambda p: p["distance_m"])
    return {**c, "results": results[:10], "origin": {"lat": origin[0], "lng": origin[1]}, "evaluated_at": now.isoformat(timespec="minutes")}
