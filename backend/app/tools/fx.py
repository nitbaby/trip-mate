import httpx

from ..config import get_settings
from .cache import TTL, cached

MOCK_USD = {"USD": 1.0, "EUR": 0.92, "GBP": 0.79, "JPY": 151.0, "INR": 83.2, "AUD": 1.52, "CAD": 1.36}


def _rate(frm: str, to: str) -> tuple[float, str]:
    if get_settings().live_mode == "real":
        with httpx.Client(timeout=10, follow_redirects=True) as h:
            r = h.get("https://api.frankfurter.dev/v1/latest", params={"base": frm, "symbols": to}).json()
        return r["rates"][to], "frankfurter"
    if frm not in MOCK_USD or to not in MOCK_USD:
        raise ValueError(f"Mock rates only cover {sorted(MOCK_USD)}")
    return MOCK_USD[to] / MOCK_USD[frm], "mock"


def convert_currency(amount: float, from_currency: str, to_currency: str) -> dict:
    frm, to = from_currency.upper(), to_currency.upper()
    if len(frm) != 3 or len(to) != 3:
        raise ValueError("Use 3-letter currency codes")
    if frm == to:
        rate, src = 1.0, "identity"
        payload = {"rate": rate, "source": src}
        return {**payload, "amount": amount, "from": frm, "to": to, "converted": round(amount, 2),
                "last_updated": None, "cached": False, "stale": False}
    c = cached(f"fx:{get_settings().live_mode}:{frm}:{to}", TTL["fx"],
               lambda: dict(zip(("rate", "source"), _rate(frm, to))))
    return {**c, "amount": amount, "from": frm, "to": to, "converted": round(amount * c["rate"], 2)}
