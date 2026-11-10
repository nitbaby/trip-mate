import re


def _units(text: str, max_chars: int, overlap: int) -> list[tuple[str, str]]:
    """Split into (separator, unit): paragraphs, falling back to lines, then to windows with overlap."""
    out: list[tuple[str, str]] = []
    for p in (p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()):
        sep = "\n\n"
        parts = [p] if len(p) <= max_chars else p.split("\n")
        for part in parts:
            part = part.strip()
            if not part:
                continue
            if len(part) > max_chars:
                step = max_chars - overlap
                for i in range(0, len(part), step):
                    out.append((sep, part[i : i + max_chars]))
                    sep = "\n"
            else:
                out.append((sep, part))
            sep = "\n"
    return out


def chunk_page(text: str, max_chars: int = 450, overlap: int = 80) -> list[str]:
    """Paragraph-level chunks (~450 chars) so a citation points at a specific passage, not a whole page."""
    chunks: list[str] = []
    cur = ""
    for sep, u in _units(text, max_chars, overlap):
        if cur and len(cur) + len(sep) + len(u) > max_chars:
            chunks.append(cur)
            cur = u
        else:
            cur = f"{cur}{sep}{u}" if cur else u
    if cur:
        chunks.append(cur)
    return chunks
