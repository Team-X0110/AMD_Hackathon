"""
tests/test_cache.py — Unit tests for exact_cache and semantic_cache.
Tests run against real Firestore using a dedicated "test_cache" collection.
Clean up after themselves — won't pollute production collections.

Run:
    cd hybrid-router-cache
    python -m pytest tests/test_cache.py -v
"""
import time
import pytest

# NOTE: These tests hit real Firestore. Set FIREWORKS_API_KEY and FIREBASE_KEY_PATH.
from src.cache.exact_cache import normalize, hash_key, get_cached, set_cached
from src.cache.firestore_client import get_db

TEST_COLLECTION = "test_cache_ci"


# ── Helpers ───────────────────────────────────────────────────────────────────

def cleanup(key: str) -> None:
    """Delete a test doc so we don't leave junk in RTDB."""
    get_db().child(TEST_COLLECTION).child(key).delete()


# ── normalize() ───────────────────────────────────────────────────────────────

def test_normalize_lowercases():
    assert normalize("Hello World") == "hello world"


def test_normalize_strips_whitespace():
    assert normalize("  hello   world  ") == "hello world"


def test_normalize_collapses_internal_spaces():
    assert normalize("hello   world") == "hello world"


def test_normalize_combined():
    assert normalize("  BUILD   AN   API  ") == "build an api"


# ── hash_key() ────────────────────────────────────────────────────────────────

def test_hash_key_deterministic():
    assert hash_key("hello") == hash_key("hello")


def test_hash_key_case_insensitive():
    assert hash_key("HELLO") == hash_key("hello")


def test_hash_key_whitespace_insensitive():
    assert hash_key("hello  world") == hash_key("hello world")


def test_hash_key_different_inputs_differ():
    assert hash_key("hello") != hash_key("world")


# ── get_cached / set_cached ───────────────────────────────────────────────────

def test_round_trip():
    key = hash_key("test_round_trip_unique_42")
    try:
        set_cached(TEST_COLLECTION, key, {"value": "world"})
        doc = get_cached(TEST_COLLECTION, key)
        assert doc is not None
        assert doc["value"] == "world"
    finally:
        cleanup(key)


def test_miss_returns_none():
    key = hash_key("this_key_should_never_exist_xyzzy")
    cleanup(key)  # ensure it's gone
    assert get_cached(TEST_COLLECTION, key) is None


def test_normalization_gives_same_cache_key():
    """'HELLO  ' and 'hello' should hit the same cache entry."""
    key = hash_key("hello normtest")
    try:
        set_cached(TEST_COLLECTION, hash_key("hello normtest"), {"value": "norm_ok"})
        # Lookup with different casing + extra space
        doc = get_cached(TEST_COLLECTION, hash_key("HELLO  normtest"))
        assert doc is not None, "Normalization should map HELLO normtest → same key"
        assert doc["value"] == "norm_ok"
    finally:
        cleanup(key)



def test_set_cached_with_embedding():
    key = hash_key("embedding_test_unique_88")
    try:
        emb = [0.1, 0.2, 0.3]
        set_cached(TEST_COLLECTION, key, {"value": "with_emb"}, embedding=emb)
        doc = get_cached(TEST_COLLECTION, key)
        assert doc is not None
        assert doc["embedding"] == emb
    finally:
        cleanup(key)
