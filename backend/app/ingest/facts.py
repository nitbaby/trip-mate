import re

from .mask import find_sensitive

FACT_PATTERNS = [
    ("Check-in", r"check-?in(?: time)?\s*[:\-]?\s*(?:from\s*)?(\d{1,2}(?::\d{2})?\s*(?:am|pm)?|\d{1,2}:\d{2})"),
    ("Check-out", r"check-?out(?: time)?\s*[:\-]?\s*(?:by|before\s*)?\s*(\d{1,2}(?::\d{2})?\s*(?:am|pm)?|\d{1,2}:\d{2})"),
    ("Breakfast", r"(breakfast[^.\n]{0,60})"),
    ("Hotel", r"^\s*(?:hotel|property)\s*:\s*([^\n]{3,60})"),
    ("Flight", r"\b(?:flight)\s*[:#]?\s*([A-Z]{2}\s?\d{2,4})\b"),
]

SENSITIVE_LABELS = {
    "passport_number": "Passport number",
    "booking_reference": "Booking reference",
    "card_number": "Card number",
}


def extract_key_facts(text: str) -> list[dict]:
    """Facts as cards. Sensitive raw values stay server-side; public_facts() strips them for the API."""
    facts = []
    for label, rx in FACT_PATTERNS:
        m = re.search(rx, text, re.IGNORECASE | re.MULTILINE)
        if m:
            facts.append({"label": label, "value": m.group(1).strip(), "sensitive": False})
    for f in find_sensitive(text):
        facts.append({"label": SENSITIVE_LABELS[f["label"]], "value": f["value"],
                      "masked": f["masked"], "sensitive": True})
    return facts


def public_facts(facts: list[dict]) -> list[dict]:
    """API view: sensitive facts expose only the masked value (DOC-05)."""
    out = []
    for i, f in enumerate(facts):
        if f.get("sensitive"):
            out.append({"index": i, "label": f["label"], "value": f["masked"], "sensitive": True})
        else:
            out.append({"index": i, "label": f["label"], "value": f["value"], "sensitive": False})
    return out
