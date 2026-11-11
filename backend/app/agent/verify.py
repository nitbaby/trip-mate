"""Deterministic grounding check: is each [n] citation supported by its passage (or by live tool results)?

A claim counts as supported when enough of its content words (and every number/time) also appear in the
evidence. This is a cheap heuristic, not a proof: it catches citations pointing at the wrong passage, not
subtle misreadings. An LLM-based check can be layered on top later."""
import re

STOP = {"a", "an", "and", "are", "as", "at", "be", "been", "by", "can", "could", "did", "do", "does", "for", "from", "had", "has", "have", "how", "i", "if", "in", "is", "it", "its", "may", "me", "my", "no", "not", "of", "on", "or", "our", "should", "so", "some", "than", "that", "the", "their", "them", "then", "there", "these", "they", "this", "to", "up", "us", "was", "we", "were", "what", "when", "where", "which", "who", "will", "with", "would", "you", "your", "yes", "please", "also", "about", "into", "over", "after", "before", "only", "any", "all", "each", "per", "via"}


MONTHS = ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december"]


def norm_times(text: str) -> str:
    """12-hour clock and ISO times become one form: '6:35 PM' and '...T18:35:00' both give '18:35'.
    ISO dates become the written form: '2026-11-30' gives '30 november 2026' (documents usually write it that way)."""
    text = re.sub(r"\b(\d{4})-(0[1-9]|1[0-2])-(\d{2})\b", lambda m: f"{int(m.group(3))} {MONTHS[int(m.group(2)) - 1]} {m.group(1)}", text)
    text = re.sub(r"(\d)T(\d)", r"\1 \2", text)

    def fix(m: re.Match) -> str:
        h, mins, ap = int(m.group(1)) % 12, m.group(2) or "00", m.group(3).lower()
        return f"{h + (12 if ap == 'pm' else 0):02d}:{mins}"

    return re.sub(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b", fix, text, flags=re.IGNORECASE)


def content_words(text: str) -> list[str]:
    out = []
    for w in re.findall(r"[a-z0-9]+(?::[0-9]{2})?", norm_times(text).lower()):
        if w in STOP:
            continue
        if len(w) > 4 and w.endswith("s") and not w.endswith("ss"):
            w = w[:-1]
        out.append(w)
    return out


def _claims(segment: str) -> list[tuple[str, str]]:
    """(marker, claim text) pairs. A claim is the text between the previous marker and this one, so
    'Check-out is 11 AM [2], and breakfast is included [1].' checks each half against its own passage.
    Adjacent markers ('[1][2]') share the claim before them."""
    parts = re.split(r"\[(\d+)\]", segment)  # text, marker, text, marker, ..., text
    pairs, last_claim = [], ""
    for i in range(1, len(parts), 2):
        claim = parts[i - 1].strip(" ,;:-") or last_claim
        pairs.append((parts[i], claim))
        last_claim = claim
    return pairs


def verify_citations(text: str, refs: dict[int, dict], evidence: list[str] | None = None, threshold: float = 0.35) -> dict[str, bool]:
    """Return {marker_number: supported}. A marker is supported if it supports at least one claim citing it."""
    pool_extra = set(content_words(" ".join(evidence or [])))

    def supports(claim: str, ref_text: str) -> bool:
        words = content_words(claim)
        if not words:
            return True
        pool = set(content_words(ref_text)) | pool_extra
        numbers = [w for w in words if any(c.isdigit() for c in w)]
        return sum(w in pool for w in words) / len(words) >= threshold and all(n in pool for n in numbers)

    support: dict[str, bool] = {}
    prev = ""  # previous sentence: models often put the marker after a sentence like "This is in the documents [1]."
    for seg in re.split(r"(?<=[.!?])\s+|\n+", text):
        for m, claim in _claims(seg):
            ref = refs.get(int(m))
            if ref is None:
                continue
            ok = supports(claim, ref["text"]) or (bool(prev) and supports(f"{prev} {claim}", ref["text"]))
            support[m] = support.get(m, False) or ok
        prev = re.sub(r"\[\d+\]", "", seg).strip()
    return support
