import re

# (label, regex, group index to mask)
PATTERNS = [
    ("passport_number", re.compile(r"(?i)passport(?:\s*(?:no\.?|number|#))?\s*[:#]?\s*([A-Z0-9]{6,9})\b"), 1),
    ("booking_reference", re.compile(r"(?i)(?:confirmation|booking|reservation|reference|PNR)\s*(?:no\.?|number|code|ref|#)?\s*[:#]?\s*([A-Z0-9]{5,10})\b"), 1),
    ("card_number", re.compile(r"\b((?:\d[ -]?){12,15}\d)\b"), 1),
]


def mask_value(v: str, keep: int = 2) -> str:
    return "•" * max(len(v) - keep, 4) + v[-keep:]


def find_sensitive(text: str) -> list[dict]:
    """Return sensitive fields: label, raw value (server side only), masked value."""
    out, seen = [], set()
    for label, rx, g in PATTERNS:
        for m in rx.finditer(text):
            val = m.group(g)
            # booking refs must contain a digit to avoid matching plain words
            if label == "booking_reference" and not any(c.isdigit() for c in val):
                continue
            if (label, val) in seen:
                continue
            seen.add((label, val))
            out.append({"label": label, "value": val, "masked": mask_value(val)})
    return out


def redact(text: str) -> str:
    """Mask sensitive values inside free text (used for logs / pre-cloud redaction)."""
    for f in find_sensitive(text):
        text = text.replace(f["value"], f["masked"])
    return text
