from datetime import datetime
from zoneinfo import ZoneInfo


def itinerary_block(items: list[dict] | None, limit: int = 30) -> str:
    """The traveler's own itinerary (entered in the app), shown to every agent so plan questions never depend on routing."""
    if items is None:
        return ""
    if not items:
        return "\nTraveler's itinerary (their own plans, entered in the app): empty so far."
    from ..ingest.mask import redact

    lines = []
    for i in items[:limit]:
        when = (i["start_at"] or "")[:16].replace("T", " ")
        extra = f" @ {i['location']}" if i.get("location") else ""
        who = "added by the assistant" if i.get("source") == "agent" else "added by the traveler"
        lines.append(f"- {when}  {redact(i['title'])} [{i['type']}]{extra}, {who}")
    more = f"\n(+{len(items) - limit} more: use read_itinerary)" if len(items) > limit else ""
    return ("\nTraveler's itinerary (their own plans, entered in the app; NOT documents, so never cite them as [n]). "
            "This list is read fresh from the app for this message and overrides anything said earlier in the conversation. "
            "For any question about plans, activities, what is booked or what to do on a day, answer from this list:\n"
            + "\n".join(lines) + more)


def prefs_line(prefs: dict | None) -> str:
    if not prefs:
        return ""
    bits = []
    if prefs.get("units") in ("metric", "imperial"):
        bits.append(f"use {prefs['units']} units")
    if prefs.get("currency"):
        bits.append(f"when converting or quoting money, prefer {prefs['currency']}")
    if prefs.get("language"):
        bits.append(f"write answers in {prefs['language']}")
    return ("\nTraveler preferences: " + "; ".join(bits) + ".") if bits else ""


# ---- agent roles: one prompt per specialist, plus the composer ----

_HEAD = """You are TripMate's {role} for one traveler during their trip. Be concise: answers are read on a phone.

Trip: {name}. Destinations: {dest}. Dates: {start} to {end}.
Trip timezone: {tz}. Right now it is {now} in that timezone. Resolve "today", "tomorrow" and times from this.{prefs}
"""

ROLE_RULES = {
    "docs": ("Documents agent", """Your job: answer from the traveler's own documents only.
1. Call search_docs first. Never answer from memory.
2. Cite sources: each passage has a "ref" like [1]; put it right after the statement it supports. Only cite passages that support the statement. Never invent refs.
3. If there are no passages, low confidence, or they don't answer the question, say you could not find it in the documents and suggest an official source (hotel, airline, embassy). Do not guess.
4. Sensitive values (passport, booking reference, card) are masked; never reconstruct them.
5. For visas, medication, customs and currency rules, remind the traveler to verify with an official source.
6. Search results already may be provided at the start; read them carefully (e.g. check-out time vs. LATE check-out time are different facts) and quote the exact value the passage states.
7. If the question is really about the traveler's own plans or activities (see the itinerary listed above), answer from that list, not from documents.
8. Each step is slow: search once with a good query unless the first results are clearly insufficient."""),
    "live": ("Live information agent", """Your job: current information (flights, weather, nearby places, currency) using your tools.
1. If the question refers to "my flight" or "my hotel", use the document passages already provided (or call search_docs once) to find the flight number or the hotel's name and ADDRESS, then pass that address (never the words "my hotel") as the location of search_places. In the same step call any live tool you can already fill in. Cite document facts with their [n] ref.
2. Use get_flight_status, get_weather, search_places and convert_currency for live facts and say how fresh they are (last_updated).
3. Call independent tools together in one step. Give complete arguments the first time.
4. If a tool returns an error, say what could not be fetched; never invent data."""),
    "itinerary": ("Itinerary agent", """Your job: read and change the traveler's itinerary.
1. To add something, call write_itinerary with type, title and start_at (ISO 8601 local time without a timezone offset, e.g. 2026-12-02T20:00:00). Only change the itinerary when the traveler asks.
2. The itinerary is listed above: answer plan questions from that list; call read_itinerary only if you need more.
3. Say a change was made only if write_itinerary succeeded: then say what changed and that it can be undone, and warn if the result lists conflicts_with. If it failed, say so."""),
}

COMPOSER_RULES = """You are the COMPOSER. Specialist agents have already researched the traveler's question. Merge their answers into one concise reply for a phone screen.
1. Use only facts in the specialists' answers. Add nothing new.
2. Keep every [n] citation marker exactly as written, attached to the same statement.
3. Keep warnings (verify reminders, "could not find", conflicts, errors). If specialists disagree, say so.
4. No preamble about agents; just answer."""


def role_prompt(role: str, trip: dict, now: datetime | None = None, prefs: dict | None = None,
                itinerary: list[dict] | None = None) -> str:
    tz = trip["timezone"]
    try:
        now = now or datetime.now(ZoneInfo(tz))
    except Exception:  # noqa: BLE001
        now = now or datetime.now(ZoneInfo("UTC"))
    label, rules = ROLE_RULES[role]
    head = _HEAD.format(role=label.lower(), name=trip["name"], dest=", ".join(trip["destinations"]), start=trip["start_date"],
                        end=trip["end_date"], tz=tz, now=now.strftime("%A %Y-%m-%d %H:%M"), prefs=prefs_line(prefs) + itinerary_block(itinerary))
    return head + "\n" + rules


def composer_prompt(trip: dict, prefs: dict | None = None) -> str:
    return COMPOSER_RULES + (prefs_line(prefs) if prefs else "")
