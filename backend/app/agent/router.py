"""Deterministic intent router: picks which specialist agents handle a question (no LLM call, so no added latency).

Order of the result is stable: docs, live, itinerary. Unmatched questions go to the docs agent, because
the safest default is "look in the traveler's documents and admit if it isn't there"."""
import json
import re

AGENTS = {
    "docs": {"label": "Documents agent", "tools": {"search_docs"}},
    # live also gets search_docs (read-only) to resolve "my flight" / "my hotel" from the documents
    "live": {"label": "Live info agent",
             "tools": {"search_docs", "get_flight_status", "get_weather", "search_places", "convert_currency"}},
    "itinerary": {"label": "Itinerary agent", "tools": {"read_itinerary", "write_itinerary"}},
}

LIVE = re.compile(r"\bflights?\b|\bdelay(?:s|ed)?\b|\bgate\b|\bterminal\b|\bweather\b|\bforecast\b|\brain(?:ing|y)?\b|\btemperature\b|\bumbrella\b|"
                  r"\bvegetarian\b|\bvegan\b|\brestaurants?\b|\bfood\b|\beat\b|\bnearby\b|near me|near my|open now|\bcafes?\b|\bconvert\b|"
                  r"exchange rate|\bcurrency\b|\b(usd|jpy|eur|gbp|inr)\b|how much is", re.IGNORECASE)
ITIN = re.compile(r"\b(add|book|schedule|cancel|remove|delete|move|reschedule|change)\b.*\b(itinerary|reservation|dinner|lunch|meeting|activity|tour)\b|"
                  r"itinerary|plan today|today's plan|what's on|my schedule|agenda|\bplans?\b|\bplanned\b|\bbooked\b|\bscheduled\b|"
                  r"things to do|what should i do|what do i have|\bactivit(?:y|ies)\b|sightseeing", re.IGNORECASE)
# patterns that mean "look it up in my documents" even when a live or itinerary word is also present
ADD_REQUEST = re.compile(r"^\W*(?:please |can you |could you )?(?:add|schedule|book|create|put)\b|"
                         r"\b(?:add|schedule|put)\b.{0,60}\b(?:to|on|in) (?:my |the )?(?:itinerary|schedule|plan)\b", re.IGNORECASE)
DOCS_STRONG = re.compile(r"check-?\s?out|check-?\s?in|breakfast|\brules?\b|\bvisas?\b|customs|medic|policy|baggage|luggage|"
                         r"cancellation|passport|confirmation|booking ref|wi-?fi|document|\bpdf\b|"
                         r"\bterminal\b|\bbags?\b|\bseat|boarding|\bfly\b|outbound|return flight|\btips?\b|\bguide\b|suica|pasmo|"
                         r"\btrains?\b|subway|metro|police|ambulance|emergency|\batm\b|tax-free|tipping", re.IGNORECASE)
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


# a weak docs word ("hotel") normally settles the route (docs), but with a proximity phrase the question is probably about places
NEAR_HINT = re.compile(r"\b(?:close to|close by|next to|around|walking distance|short walk|nearest|closest)\b", re.IGNORECASE)


def matched_any(message: str) -> bool:
    """True when a rule settles the route. A total miss, or only a weak docs word next to a proximity phrase
    ("coffee shops close to my hotel"), is the only case the optional LLM fallback is asked about."""
    if any(p.search(message) for p in (LIVE, ITIN, ADD_REQUEST, DOCS_STRONG)):
        return True
    return bool(DOCS_WEAK.search(message)) and not NEAR_HINT.search(message)


ROUTER_PROMPT = """You route questions for a travel assistant. Decide which specialists are needed to answer the traveler's latest message.
- "docs": the traveler's own documents and the travel guide: hotel, flights, bookings, rules, visas, customs, etiquette, tipping, local practices, transport and safety tips, emergency numbers.
- "live": only current, changing information: weather, flight status, nearby places or food, currency conversion.
- "itinerary": reading or changing the traveler's day-by-day plan.
Questions about how things normally work or what is customary are "docs", not "live". Choose only what is needed. If unsure, answer docs.
Reply with JSON only, for example {"intents": ["live"]}."""


def widen_fallback(intents: list[str]) -> list[str]:
    """A live-only answer from the LLM fallback also gets the documents agent: a mis-route to live (e.g. a tipping question)
    would otherwise never look in the documents. Used only for fallback routes, never for rule matches."""
    return ["docs", "live"] if intents == ["live"] else intents


def parse_intents(text: str) -> list[str]:
    """Model reply -> intents in the stable order docs, live, itinerary. Anything unusable -> ["docs"] (the rules' own default)."""
    m = re.search(r"\{.*\}", text or "", re.DOTALL)
    try:
        data = json.loads(m.group(0)) if m else {}
        wanted = data.get("intents") if isinstance(data, dict) else None
    except ValueError:
        wanted = None
    if not isinstance(wanted, list):
        return ["docs"]
    return [a for a in AGENTS if a in wanted] or ["docs"]  # allowlist: the model can't invent an agent
