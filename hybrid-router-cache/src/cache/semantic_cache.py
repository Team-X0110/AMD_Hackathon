"""
cache/semantic_cache.py — Embedding-based semantic cache. (Now uses Realtime DB)
"""
from __future__ import annotations

import numpy as np

from src.cache.firestore_client import get_db
from src.cache.exact_cache import normalize
from src.fireworks_client import get_embedding
from src.config import SEMANTIC_THRESHOLD, CACHE_LOOKBACK_LIMIT


def cosine_sim(a: list[float], b: list[float]) -> float:
    """Return cosine similarity in [0, 1]. Returns 0.0 if either vector is zero."""
    va = np.array(a, dtype=np.float32)
    vb = np.array(b, dtype=np.float32)
    denom = float(np.linalg.norm(va) * np.linalg.norm(vb))
    if denom == 0.0:
        return 0.0
    return float(np.dot(va, vb) / denom)


def semantic_lookup(
    collection: str,
    query_text: str,
) -> tuple[dict | None, float]:
    """
    Search the collection for the most semantically similar cached entry.
    """
    query_emb = get_embedding(normalize(query_text))

    # Fetch recent cache entries (no index required — sort in Python)
    ref = get_db().child(collection)
    raw = ref.get()

    if not raw:
        return None, 0.0

    # Sort by created_at descending, take last CACHE_LOOKBACK_LIMIT
    items = [(k, v) for k, v in raw.items() if isinstance(v, dict)]
    items.sort(key=lambda x: x[1].get("created_at", 0), reverse=True)
    items = items[:CACHE_LOOKBACK_LIMIT]

    results = {k: v for k, v in items}

    best_doc: dict | None = None
    best_score: float = 0.0

    # results is an OrderedDict mapping keys to dicts
    for key, d in results.items():
        if not isinstance(d, dict) or "embedding" not in d:
            continue
        
        score = cosine_sim(query_emb, d["embedding"])
        if score > best_score:
            best_doc, best_score = d, score

    if best_score >= SEMANTIC_THRESHOLD:
        return best_doc, best_score

    return None, best_score
