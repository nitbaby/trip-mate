import hashlib
import math
import re

from ..config import get_settings

_model = None
DIM = 384


def _hash_embed(text: str) -> list[float]:
    """Deterministic bag-of-words hashing embedding. Test/offline only."""
    v = [0.0] * DIM
    for w in re.findall(r"[a-z0-9]+", text.lower()):
        h = int(hashlib.md5(w.encode()).hexdigest(), 16)
        v[h % DIM] += 1.0
    n = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / n for x in v]


def embed(texts: list[str]) -> list[list[float]]:
    global _model
    if get_settings().embeddings == "hash":
        return [_hash_embed(t) for t in texts]
    if get_settings().embeddings == "fastembed":
        if _model is None:
            from fastembed import TextEmbedding

            _model = TextEmbedding("BAAI/bge-small-en-v1.5")  # needs huggingface.co / GCS access
        return [list(map(float, e)) for e in _model.embed(texts)]
    # default "onnx": all-MiniLM-L6-v2 via Chroma's bundled ONNX runner (downloads from AWS S3, ~80 MB, once)
    if _model is None:
        from chromadb.utils.embedding_functions import ONNXMiniLM_L6_V2

        _model = ONNXMiniLM_L6_V2()
    return [list(map(float, e)) for e in _model(texts)]
