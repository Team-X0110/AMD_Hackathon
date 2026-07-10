"""In-process cache fallback when Firebase RTDB is unavailable."""
from __future__ import annotations

_memory: dict[str, dict[str, dict]] = {}


def memory_get(collection: str, key: str) -> dict | None:
    bucket = _memory.get(collection, {})
    data = bucket.get(key)
    return data if isinstance(data, dict) else None


def memory_set(collection: str, key: str, data: dict) -> None:
    _memory.setdefault(collection, {})[key] = data


def memory_list(collection: str) -> dict[str, dict]:
    return dict(_memory.get(collection, {}))
