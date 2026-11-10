"""Confidence check over retrieval results (spec 7.3): top score plus whether the top chunks agree."""
from .config import get_settings


def assess(hits: list[dict]) -> tuple[str, list[dict]]:
    """Return (level, usable_hits). level in high|low|none. Hits below conf_low are dropped."""
    s = get_settings()
    strong = [h for h in hits if h["score"] >= s.conf_low]
    if not strong:
        return "none", []
    top = strong[0]
    # Sibling chunks of the best document also come along when they score a little lower: a fact (e.g. the
    # "Check-out: 11:00 AM" line in a booking header) often sits in a different chunk than the best match.
    usable = strong + [h for h in hits if h not in strong and h["document_id"] == top["document_id"]
                       and h["score"] >= s.conf_low - s.conf_sibling_margin]
    usable.sort(key=lambda h: -h["score"])
    if top["score"] >= s.conf_high:
        return "high", usable
    if top["score"] >= s.conf_agree and any(
        h["document_id"] == top["document_id"] and h is not top for h in strong[1:]
    ):
        return "high", usable
    return "low", usable
