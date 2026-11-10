"""Confidence check over retrieval results (spec 7.3): top score plus whether the top chunks agree."""
from .config import get_settings


def assess(hits: list[dict]) -> tuple[str, list[dict]]:
    """Return (level, usable_hits). level in high|low|none. Hits below conf_low are dropped."""
    s = get_settings()
    usable = [h for h in hits if h["score"] >= s.conf_low]
    if not usable:
        return "none", []
    top = usable[0]
    if top["score"] >= s.conf_high:
        return "high", usable
    if top["score"] >= s.conf_agree and any(
        h["document_id"] == top["document_id"] and h is not top for h in usable[1:]
    ):
        return "high", usable
    return "low", usable
