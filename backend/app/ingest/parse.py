from pathlib import Path

from pypdf import PdfReader


def parse_file(path: Path) -> list[tuple[int, str]]:
    """Return [(page_number, text)]; plain text files are a single page 1."""
    if path.suffix.lower() == ".pdf":
        reader = PdfReader(str(path))
        pages = [(i + 1, (p.extract_text() or "").strip()) for i, p in enumerate(reader.pages)]
    else:
        pages = [(1, path.read_text(encoding="utf-8", errors="replace").strip())]
    pages = [(n, t) for n, t in pages if t]
    if not pages:
        raise ValueError("No extractable text found in document")
    return pages
