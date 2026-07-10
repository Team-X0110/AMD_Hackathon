"""cache/__init__.py — Public re-exports for the cache layer."""
from src.cache.firestore_client import get_db
from src.cache.exact_cache import normalize, hash_key, get_cached, set_cached
from src.cache.semantic_cache import cosine_sim, semantic_lookup

__all__ = [
    "get_db",
    "normalize",
    "hash_key",
    "get_cached",
    "set_cached",
    "cosine_sim",
    "semantic_lookup",
]
