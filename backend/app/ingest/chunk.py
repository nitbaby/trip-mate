import re


def chunk_page(text: str, max_chars: int = 900, overlap: int = 150) -> list[str]:
    """Paragraph-aware chunking: pack paragraphs up to max_chars, split long ones with overlap."""
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks, cur = [], ""
    for p in paras:
        if len(p) > max_chars:
            if cur:
                chunks.append(cur)
                cur = ""
            step = max_chars - overlap
            chunks.extend(p[i : i + max_chars] for i in range(0, len(p), step))
        elif len(cur) + len(p) + 2 <= max_chars:
            cur = f"{cur}\n\n{p}" if cur else p
        else:
            chunks.append(cur)
            cur = p
    if cur:
        chunks.append(cur)
    return chunks
