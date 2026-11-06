import json
import shutil
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, UploadFile

from .. import vectors
from ..config import get_settings
from ..db import connect, new_id, now_iso
from ..errors import ApiError, not_found
from ..ingest.pipeline import ingest_document

router = APIRouter(tags=["documents"])
ALLOWED = {".pdf", ".txt", ".md"}
MAX_BYTES = 10 * 1024 * 1024


@router.post("/api/trips/{trip_id}/documents", status_code=202)
async def upload(trip_id: str, file: UploadFile, bg: BackgroundTasks):
    with connect() as c:
        if not c.execute("SELECT 1 FROM trips WHERE id=?", (trip_id,)).fetchone():
            raise not_found("Trip")
        name = Path(file.filename or "upload").name  # strip any path components
        if Path(name).suffix.lower() not in ALLOWED:
            raise ApiError("VALIDATION_FAILED", "Only PDF, TXT and MD files are supported", 422)
        data = await file.read()
        if len(data) > MAX_BYTES:
            raise ApiError("VALIDATION_FAILED", "File exceeds 10 MB", 422)
        doc_id = new_id()
        d = get_settings().uploads_dir / doc_id
        d.mkdir(parents=True)
        (d / name).write_bytes(data)
        c.execute("INSERT INTO documents(id,trip_id,filename,doc_type,status,uploaded_at) VALUES (?,?,?,?,?,?)",
                  (doc_id, trip_id, name, None, "queued", now_iso()))
    bg.add_task(ingest_document, doc_id)
    return {"id": doc_id, "filename": name, "status": "queued"}


@router.get("/api/trips/{trip_id}/documents/{doc_id}/status")
def status(trip_id: str, doc_id: str):
    with connect() as c:
        r = c.execute("SELECT id,status,doc_type,error FROM documents WHERE id=? AND trip_id=?",
                      (doc_id, trip_id)).fetchone()
        if not r:
            raise not_found("Document")
        return dict(r)


@router.get("/api/documents/{doc_id}/chunks/{chunk_id}")
def chunk(doc_id: str, chunk_id: str):
    """Source Drawer content: the chunk plus surrounding chunks on the same document."""
    with connect() as c:
        r = c.execute("""SELECT ch.*, d.filename FROM chunks ch JOIN documents d ON d.id=ch.document_id
                         WHERE ch.id=? AND ch.document_id=?""", (chunk_id, doc_id)).fetchone()
        if not r:
            raise not_found("Chunk")
        around = [dict(x) for x in c.execute(
            "SELECT id,page,text FROM chunks WHERE document_id=? AND page=? ORDER BY rowid", (doc_id, r["page"]))]
        return {"chunk_id": r["id"], "document_id": doc_id, "document_name": r["filename"],
                "page": r["page"], "text": r["text"], "surrounding": around}


@router.get("/api/documents/{doc_id}/facts/{index}/reveal")
def reveal(doc_id: str, index: int):
    """DOC-06: raw value returned only on explicit tap; client re-masks after 30s."""
    with connect() as c:
        r = c.execute("SELECT key_facts FROM documents WHERE id=?", (doc_id,)).fetchone()
        if not r:
            raise not_found("Document")
        facts = json.loads(r["key_facts"])
        if index < 0 or index >= len(facts) or not facts[index].get("sensitive"):
            raise not_found("Sensitive fact")
        return {"value": facts[index]["value"], "reveal_seconds": 30}


@router.delete("/api/trips/{trip_id}/documents/{doc_id}", status_code=204)
def delete(trip_id: str, doc_id: str):
    with connect() as c:
        if not c.execute("SELECT 1 FROM documents WHERE id=? AND trip_id=?", (doc_id, trip_id)).fetchone():
            raise not_found("Document")
        c.execute("DELETE FROM documents WHERE id=?", (doc_id,))
    vectors.delete_document(doc_id)
    shutil.rmtree(get_settings().uploads_dir / doc_id, ignore_errors=True)
