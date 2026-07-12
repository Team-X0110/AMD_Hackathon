"""
cache/exact_cache.py — Exact hash-based cache layer. (Now uses Realtime DB)
"""
from __future__ import annotations
import hashlib
import time

from src.cache.firestore_client import get_db
from src.cache.memory_store import memory_get, memory_set


def normalize(text: str) -> str:
    """Normalize prompt text for exact matching."""
    return " ".join(text.lower().split())


def hash_key(text: str) -> str:
    """Generate SHA-256 hex digest for cache key."""
    return hashlib.sha256(normalize(text).encode("utf-8")).hexdigest()


def get_cached(collection: str, key: str) -> dict | None:
    """Get exact cache hit from RTDB, with in-memory fallback."""
    try:
        ref = get_db().child(collection).child(key)
        data = ref.get()
        return data if isinstance(data, dict) else None
    except Exception:
        return memory_get(collection, key)


def set_cached(
    collection: str,
    key: str,
    data: dict,
    embedding: list[float] | None = None,
) -> None:
    """Set cache entry in RTDB, with in-memory fallback."""
    doc = {
        **data,
        "created_at": int(time.time()),
    }
    if embedding is not None:
        doc["embedding"] = embedding

    try:
        get_db().child(collection).child(key).set(doc)
    except Exception as exc:
        print(f"[cache] RTDB unavailable, using in-memory cache: {exc}")
        memory_set(collection, key, doc)
