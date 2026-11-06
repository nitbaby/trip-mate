import chromadb

from .config import get_settings
from .ingest.embed import embed

_client = None


def _col():
    global _client
    s = get_settings()
    if _client is None or getattr(_client, "_tm_dir", None) != str(s.chroma_dir):
        _client = chromadb.PersistentClient(path=str(s.chroma_dir))
        _client._tm_dir = str(s.chroma_dir)
    return _client.get_or_create_collection("chunks", metadata={"hnsw:space": "cosine"})


def add_chunks(rows: list[dict]) -> None:
    """rows: id, text, trip_id, doc_type, document_id"""
    if not rows:
        return
    _col().upsert(
        ids=[r["id"] for r in rows],
        embeddings=embed([r["text"] for r in rows]),
        documents=[r["text"] for r in rows],
        metadatas=[{k: r[k] for k in ("trip_id", "doc_type", "document_id")} for r in rows],
    )


def delete_document(document_id: str) -> None:
    _col().delete(where={"document_id": document_id})


def query(trip_id: str, text: str, k: int = 5, doc_type: str | None = None) -> list[dict]:
    where = {"trip_id": trip_id} if not doc_type else {"$and": [{"trip_id": trip_id}, {"doc_type": doc_type}]}
    res = _col().query(query_embeddings=embed([text]), n_results=k, where=where)
    out = []
    for i, cid in enumerate(res["ids"][0]):
        out.append({"chunk_id": cid, "text": res["documents"][0][i],
                    "score": 1.0 - float(res["distances"][0][i]),  # cosine similarity
                    **res["metadatas"][0][i]})
    return out
