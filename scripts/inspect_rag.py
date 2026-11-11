"""Visual, READ-ONLY look inside the RAG store (Chroma) as one self-contained HTML page.

  .venv/bin/python scripts/inspect_rag.py [--out rag_report.html] [--trip TRIP_ID] [--query "what time is check-out"]
  open rag_report.html

Shows: the collection (count, dimension, distance space), documents and their chunks (text, metadata, first
embedding values), a 2-D map of all chunk embeddings (PCA, coloured by document; hover for text) and, with
--query, the top hits with cosine scores and the confidence level the agent would compute.

Sensitive values (passport, booking reference, card) are masked in the report unless you pass --raw: the
index itself stores the raw text and only the app masks it on the way out.

Safe for your data: the Chroma folder is COPIED to a temp dir first and the SQLite file is opened read-only.
It uses the same settings as the backend (TRIPMATE_DATA_DIR, EMBEDDINGS), so for --query use the same
EMBEDDINGS value that built the index (default onnx)."""
import argparse
import html
import shutil
import sqlite3
import sys
import tempfile
from collections import defaultdict
from pathlib import Path

import chromadb
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
from app.config import get_settings  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--out", default="rag_report.html")
ap.add_argument("--trip", help="only this trip id")
ap.add_argument("--query", help="also score this question against the index")
ap.add_argument("--raw", action="store_true", help="show sensitive values (passport, booking ref, card) unmasked; the store keeps them raw")
a = ap.parse_args()

s = get_settings()
src = Path(s.chroma_dir)
if not src.exists():
    sys.exit(f"No Chroma store at {src}. Upload a document first (or set TRIPMATE_DATA_DIR).")
tmp = Path(tempfile.mkdtemp(prefix="tm-chroma-"))
shutil.copytree(src, tmp / "chroma")
client = chromadb.PersistentClient(path=str(tmp / "chroma"))
cols = client.list_collections()
col = client.get_collection("chunks")
where = {"trip_id": a.trip} if a.trip else None
got = col.get(where=where, include=["documents", "metadatas", "embeddings"])
ids, docs, metas = got["ids"], got["documents"], got["metadatas"]
emb = np.array(got["embeddings"], dtype=float) if len(ids) else np.zeros((0, 0))

names, trips = {}, {}
db = Path(s.tripmate_data_dir) / "tripmate.db"
if db.exists():
    c = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    names = {r[0]: r[1] for r in c.execute("SELECT id, filename FROM documents")}
    trips = {r[0]: r[1] for r in c.execute("SELECT id, name FROM trips")}
    n_sql = c.execute("SELECT count(*) FROM chunks").fetchone()[0]
else:
    n_sql = None

from app.ingest.mask import redact  # noqa: E402

if not a.raw:  # the index stores raw text; the app masks it on the way out, so mask it here too
    docs = [redact(d) for d in docs]
esc = html.escape
palette = ["#2563eb", "#dc2626", "#16a34a", "#d97706", "#7c3aed", "#0891b2", "#be185d", "#4b5563"]
doc_ids = sorted({m["document_id"] for m in metas})
color = {d: palette[i % len(palette)] for i, d in enumerate(doc_ids)}


def label(d):
    return names.get(d, d)


# ---- 2-D map (PCA via SVD) ----
svg = "<p>Not enough chunks for a map.</p>"
if len(ids) >= 3:
    x = emb - emb.mean(0)
    _, _, vt = np.linalg.svd(x, full_matrices=False)
    p = x @ vt[:2].T
    lo, hi = p.min(0), p.max(0)
    span = np.where(hi - lo == 0, 1, hi - lo)
    pts = (p - lo) / span * np.array([560, 340]) + np.array([20, 20])
    dots = "".join(
        f'<circle cx="{pts[i, 0]:.1f}" cy="{pts[i, 1]:.1f}" r="7" fill="{color[metas[i]["document_id"]]}" fill-opacity="0.8">'
        f'<title>{esc(label(metas[i]["document_id"]))} | {esc(docs[i][:160])}</title></circle>' for i in range(len(ids)))
    legend = "".join(f'<span style="color:{color[d]}">&#9679; {esc(label(d))}</span> &nbsp; ' for d in doc_ids)
    svg = f'<svg viewBox="0 0 600 380" width="600" height="380" style="background:#f8fafc;border:1px solid #cbd5e1">{dots}</svg><div>{legend}</div>'

# ---- query scoring ----
qhtml = ""
if a.query:
    from app.confidence import assess
    from app.ingest.embed import embed
    qv = np.array(embed([a.query])[0], dtype=float)
    sims = (emb @ qv) / (np.linalg.norm(emb, axis=1) * np.linalg.norm(qv))
    order = np.argsort(-sims)[:8]
    hits = [{"score": float(sims[i]), "document_id": metas[i]["document_id"], "i": int(i)} for i in order]
    level, usable = assess([dict(h) for h in hits])
    kept = {h["i"] for h in usable}
    rows = "".join(
        f'<tr style="{"font-weight:600" if h["i"] in kept else "color:#94a3b8"}"><td>{h["score"]:.3f}</td><td>{"returned" if h["i"] in kept else "dropped"}</td>'
        f'<td>{esc(label(h["document_id"]))}</td><td>{esc(docs[h["i"]][:200])}</td></tr>' for h in hits)
    qhtml = (f"<h2>Query: {esc(a.query)}</h2><p>Confidence the agent would compute: <b>{level}</b> "
             f"(thresholds: high &ge; {s.conf_high}, agree &ge; {s.conf_agree}, low &ge; {s.conf_low}, sibling margin {s.conf_sibling_margin}). "
             f"Embedder: <code>{esc(s.embeddings)}</code>. Note: the agent searches the whole trip; this view scores all chunks shown.</p>"
             f"<table><tr><th>cosine</th><th>status</th><th>document</th><th>chunk text</th></tr>{rows}</table>")

# ---- documents and chunks ----
by_doc = defaultdict(list)
for i, m in enumerate(metas):
    by_doc[m["document_id"]].append(i)
sections = ""
for d, idxs in by_doc.items():
    sections += (f'<h3 style="color:{color[d]}">{esc(label(d))} <small>({esc(metas[idxs[0]]["doc_type"])}, trip {esc(trips.get(metas[idxs[0]]["trip_id"], metas[idxs[0]]["trip_id"]))}, '
                 f'{len(idxs)} chunks)</small></h3><table><tr><th>chunk id</th><th>chars</th><th>text</th><th>embedding (first 6 of {emb.shape[1]})</th></tr>')
    for i in idxs:
        sections += (f"<tr><td><code>{esc(ids[i])}</code></td><td>{len(docs[i])}</td><td><pre>{esc(docs[i])}</pre></td>"
                     f"<td><code>{', '.join(f'{v:.3f}' for v in emb[i][:6])}</code></td></tr>")
    sections += "</table>"

dim = emb.shape[1] if len(ids) else 0
space = (col.metadata or {}).get("hnsw:space")
sql_note = "" if n_sql is None else f" &middot; SQLite chunk rows: <b>{n_sql}</b> ({'matches' if n_sql == col.count() else '<b style=color:#dc2626>DIFFERS from Chroma: re-run scripts/reindex.py</b>'})"
page = f"""<!doctype html><meta charset="utf-8"><title>TripMate RAG report</title>
<style>body{{font:14px system-ui;margin:24px;max-width:1100px}}table{{border-collapse:collapse;width:100%;margin:8px 0 24px}}
td,th{{border:1px solid #cbd5e1;padding:4px 8px;vertical-align:top;text-align:left}}pre{{white-space:pre-wrap;margin:0;font:12px ui-monospace}}small{{color:#64748b}}</style>
<h1>TripMate RAG report</h1>
<p>Chroma folder (copied, read-only): <code>{esc(str(src))}</code> &middot; collections: <b>{esc(', '.join(c.name for c in cols))}</b> &middot;
chunks shown: <b>{len(ids)}</b> of {col.count()} &middot; dimension: <b>{dim}</b> &middot; distance: <b>{esc(str(space))}</b>{sql_note}</p>
{qhtml}<h2>Embedding map</h2>{svg}<h2>Documents and chunks</h2>{sections}"""
Path(a.out).write_text(page)
shutil.rmtree(tmp, ignore_errors=True)
print(f"wrote {a.out}: {len(ids)} chunks, {len(by_doc)} documents, dim {dim}")
