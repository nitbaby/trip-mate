import httpx

from ..config import get_settings
from .cache import TTL, cached

WMO = {0: "clear", 1: "mostly clear", 2: "partly cloudy", 3: "overcast", 45: "fog", 51: "light drizzle",
       61: "light rain", 63: "rain", 65: "heavy rain", 71: "light snow", 73: "snow", 80: "showers", 95: "thunderstorm"}
MOCK_BASE = {"tokyo": (13, 5, "clear"), "london": (8, 4, "overcast")}


def _mock(location: str, days: int) -> dict:
    hi, lo, cond = MOCK_BASE.get(location.lower().split(",")[0].strip(), (15, 7, "partly cloudy"))
    from datetime import date, timedelta

    daily = [{"date": str(date.today() + timedelta(days=i)), "high_c": hi + (i % 3) - 1, "low_c": lo + (i % 2),
              "conditions": cond if i % 3 else "light rain", "precip_chance_pct": 10 if i % 3 else 60}
             for i in range(days)]
    return {"location": location, "daily": daily, "source": "mock"}


def _real(location: str, days: int) -> dict:
    with httpx.Client(timeout=10, follow_redirects=True) as h:
        g = h.get("https://geocoding-api.open-meteo.com/v1/search", params={"name": location, "count": 1}).json()
        if not g.get("results"):
            raise ValueError(f"Unknown location: {location}")
        r = g["results"][0]
        f = h.get("https://api.open-meteo.com/v1/forecast", params={
            "latitude": r["latitude"], "longitude": r["longitude"], "forecast_days": days, "timezone": "auto",
            "daily": "temperature_2m_max,temperature_2m_min,weather_code,precipitation_probability_max"}).json()["daily"]
    daily = [{"date": f["time"][i], "high_c": f["temperature_2m_max"][i], "low_c": f["temperature_2m_min"][i],
              "conditions": WMO.get(f["weather_code"][i], f"code {f['weather_code'][i]}"),
              "precip_chance_pct": f["precipitation_probability_max"][i]} for i in range(len(f["time"]))]
    return {"location": f"{r['name']}, {r.get('country', '')}".strip(", "), "daily": daily, "source": "open-meteo"}


def get_weather(location: str, days: int = 3) -> dict:
    days = max(1, min(int(days), 7))
    fetch = _real if get_settings().live_mode == "real" else _mock
    return cached(f"weather:{get_settings().live_mode}:{location.lower()}:{days}", TTL["weather"],
                  lambda: fetch(location, days))
