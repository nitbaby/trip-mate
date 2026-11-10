"""Re-run ingestion for all (or one) documents, e.g. after changing chunking or the embedding model.

  .venv/bin/python scripts/reindex.py            # all documents
  .venv/bin/python scripts/reindex.py <docId>
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.db import connect
from app.ingest.pipeline import ingest_document

ids = sys.argv[1:] or [r["id"] for r in connect().execute("SELECT id FROM documents")]
for i in ids:
    ingest_document(i)
    r = connect().execute("SELECT filename,status,error FROM documents WHERE id=?", (i,)).fetchone()
    n = connect().execute("SELECT count(*) n FROM chunks WHERE document_id=?", (i,)).fetchone()["n"]
    print(i, r["filename"], r["status"], f"{n} chunks", r["error"] or "")
