"""Deterministic intent router: picks which specialist agents handle a question (no LLM call, so no added latency).

Order of the result is stable: docs, live, itinerary. Unmatched questions go to the docs agent, because
the safest default is "look in the traveler's documents and admit if it isn't there"."""
import re

AGENTS = {
    "docs": {"label": "Documents agent", "tools": {"search_docs"}},
    # live also gets search_docs (read-only) to resolve "my flight" / "my hotel" from the documents
    "live": {"label": "Live info agent",
             "tools": {"search_docs", "get_flight_status", "get_weather", "search_places", "convert_currency"}},
    "itinerary": {"label": "Itinerary agent", "tools": {"read_itinerary", "write_itinerary"}},
}

LIVE = re.compile(r"flight|delay|gate|terminal|weather|forecast|rain|temperature|umbrella|vegetarian|vegan|restaurant|"
                  r"\bfood\b|\beat\b|nearby|near me|near my|open now|cafe|convert|exchange rate|currency|\b(usd|jpy|eur|gbp|inr)\b|how much is", re.IGNORECASE)
ITIN = re.compile(r"\b(add|book|schedule|cancel|remove|delete|move|reschedule|change)\b.*\b(itinerary|reservation|dinner|lunch|meeting|activity|tour)\b|"
                  r"itinerary|plan today|today's plan|what's on|my schedule|agenda|\bplans?\b|\bplanned\b|\bbooked\b|\bscheduled\b|"
                  r"things to do|what should i do|what do i have|\bactivit(?:y|ies)\b|sightseeing", re.IGNORECASE)
# patterns that mean "look it up in my documents" even when a live or itinerary word is also present
ADD_REQUEST = re.compile(r"^\W*(?:please |can you |could you )?(?:add|schedule|book|create|put)\b|"
                         r"\b(?:add|schedule|put)\b.{0,60}\b(?:to|on|in) (?:my |the )?(?:itinerary|schedule|plan)\b", re.IGNORECASE)
DOCS_STRONG = re.compile(r"check-?\s?out|check-?\s?in|breakfast|\brules?\b|\bvisas?\b|customs|medic|policy|baggage|luggage|"
                         r"cancellation|passport|confirmation|booking ref|wi-?fi|document|\bpdf\b", re.IGNORECASE)
DOCS_WEAK = re.compile(r"hotel|booking|reservation|ticket|lounge|airport|stay|room", re.IGNORECASE)


def route(message: str) -> list[str]:
    live, itin = bool(LIVE.search(message)), bool(ITIN.search(message) or ADD_REQUEST.search(message))
    docs_strong = bool(DOCS_STRONG.search(message))
    out = []
    if docs_strong or (not live and not itin):
        out.append("docs")
    if live:
        out.append("live")
    if itin:
        out.append("itinerary")
    return out
