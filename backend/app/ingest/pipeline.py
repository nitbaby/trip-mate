import json
import logging
from pathlib import Path

from .. import vectors
from ..db import connect, new_id
from .chunk import chunk_page
from .classify import classify
from .facts import extract_key_facts
from .parse import parse_file

log = logging.getLogger("tripmate.ingest")


def _set_status(conn, doc_id, status, error=None):
    conn.execute("UPDATE documents SET status=?, error=? WHERE id=?", (status, error, doc_id))
    conn.commit()


def ingest_document(doc_id: str) -> None:
    """Runs in a background task: queued -> processing -> ready | failed."""
    conn = connect()
    try:
        doc = conn.execute("SELECT * FROM documents WHERE id=?", (doc_id,)).fetchone()
        if not doc:
            return
        _set_status(conn, doc_id, "processing")
        from ..config import get_settings

        path = Path(get_settings().uploads_dir) / doc_id / doc["filename"]
        pages = parse_file(path)
        full = "\n\n".join(t for _, t in pages)
        doc_type = classify(full)
        facts = extract_key_facts(full)
        rows = []
        for page, text in pages:
            for c in chunk_page(text):
                cid = new_id()
                conn.execute("INSERT INTO chunks(id,document_id,page,text,metadata) VALUES (?,?,?,?,?)",
                             (cid, doc_id, page, c, "{}"))
                rows.append({"id": cid, "text": c, "trip_id": doc["trip_id"],
                             "doc_type": doc_type, "document_id": doc_id})
        vectors.add_chunks(rows)
        conn.execute("UPDATE documents SET doc_type=?, key_facts=? WHERE id=?",
                     (doc_type, json.dumps(facts), doc_id))
        _set_status(conn, doc_id, "ready")
    except Exception as e:
        log.exception("ingest failed for %s", doc_id)  # no document text in logs
        _set_status(conn, doc_id, "failed", str(e)[:200])
    finally:
        conn.close()
