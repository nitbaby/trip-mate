import re

# CHAT-05: topics whose answers must always carry a verify badge
VERIFY_TOPICS = [
    (r"\bvisas?\b|entry requirements?", "Visa and entry rules change; verify with the embassy or official immigration site."),
    (r"medicat|medicine|prescription|drugs?\b|pharmac", "Medication rules are strict and change; verify with the destination's health ministry or embassy."),
    (r"\bcustoms\b|duty[- ]free|declare|import limit|prohibited|restricted items?", "Customs rules change; verify with the official customs authority."),
    (r"currency (rules?|limits?|restrictions?)|cash limit|exchange control|carry(ing)? (cash|currency)", "Currency rules change; verify with official sources."),
]

EXTERNAL_TOOLS = {"get_flight_status", "get_weather", "search_places", "convert_currency"}

LABELS = {
    "search_docs": "Searching your documents", "read_itinerary": "Reading your itinerary",
    "write_itinerary": "Updating your itinerary", "get_flight_status": "Checking flight status",
    "get_weather": "Checking the weather", "search_places": "Finding places nearby",
    "convert_currency": "Converting currency",
}


def verify_reason(*texts: str) -> str | None:
    blob = " ".join(texts).lower()
    for rx, reason in VERIFY_TOPICS:
        if re.search(rx, blob):
            return reason
    return None


def summarize(name: str, args: dict, r: dict) -> str:
    if "error" in r:
        return r["error"].get("message", "failed")[:120]
    if name == "search_docs":
        return f"{len(r['results'])} passage(s), confidence {r['confidence']}"
    if name == "get_flight_status":
        d = f" by {r['delay_minutes']} min" if r.get("delay_minutes") else ""
        return f"{r['flight']} {r['status'].replace('_', ' ')}{d}"
    if name == "get_weather":
        return f"{r['location']}, {len(r['daily'])} day forecast"
    if name == "search_places":
        return f"{len(r['results'])} place(s) found"
    if name == "convert_currency":
        return f"{r['amount']} {r['from']} = {r['converted']} {r['to']}"
    if name == "read_itinerary":
        return f"{len(r['items'])} item(s)"
    if name == "write_itinerary":
        return f"{r['action']} '{r['item'].get('title', '')}'"
    return "ok"
