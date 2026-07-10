"""
agents/goal_understanding.py — Goal Understanding Agent.

Runs fully locally via Ollama (llama3.1:8b) right now.
To switch to Fireworks cloud: set LLM_BACKEND=fireworks in .env — zero code change.

Cache layers (exact → semantic → LLM):
  1. Exact cache  — SHA-256 hash match → 0 tokens, instant
  2. Semantic     — cosine similarity on embeddings → 0 tokens
  3. LLM fallback — calls Ollama or Fireworks depending on LLM_BACKEND
"""
from __future__ import annotations

from src.config import LLM_BACKEND, LOCAL_MODEL, GOAL_MODEL, GOAL_COLLECTION
from src.fireworks_client import call_llm, get_embedding
from src.cache.exact_cache import normalize, hash_key, get_cached, set_cached
from src.cache.semantic_cache import semantic_lookup
from src.validators import validate_goal_schema


# ── Which model to use per backend ────────────────────────────────────────────
def _model() -> str:
    return LOCAL_MODEL if LLM_BACKEND == "local" else GOAL_MODEL


# ── System prompt ─────────────────────────────────────────────────────────────
# Explicit JSON structure so Ollama's "format":"json" mode has a clear template.
GOAL_SYSTEM_PROMPT = """You are a Goal Understanding Agent. Analyze the user's request and return a JSON object with EXACTLY these keys:

{
  "intent": "<concise verb phrase — what the user wants to accomplish>",
  "entities": ["<key noun 1>", "<key noun 2>"],
  "constraints": ["<technical requirement>", "<non-functional concern>"],
  "success_criteria": ["<measurable condition for done>"],
  "domain": "<broad field, e.g. 'software engineering', 'data analysis', 'devops'>",
  "complexity_hint": "<exactly one of: low | medium | high>"
}

Rules:
- Output ONLY the JSON object. No prose, no markdown fences, no explanation.
- 'entities' must be a list (can be empty []).
- 'constraints' must be a list (can be empty []).
- 'success_criteria' must be a non-empty list — at least one measurable outcome.
- 'complexity_hint' must be exactly 'low', 'medium', or 'high'.
- If the input is ambiguous, make a reasonable inference and still return valid JSON."""


# ── Phase 3 — exact cache only ────────────────────────────────────────────────

def understand_goal(user_prompt: str) -> dict:
    """
    Exact cache only. Use understand_goal_with_semantic for the full pipeline.

    Returns:
        {"goal": dict, "cache_hit": "exact"|"none", "tokens_used": int}
    """
    key = hash_key(user_prompt)

    cached = get_cached(GOAL_COLLECTION, key)
    if cached:
        return {"goal": cached["goal_json"], "cache_hit": "exact", "tokens_used": 0}

    result, usage = call_llm(LLM_BACKEND, _model(), GOAL_SYSTEM_PROMPT, user_prompt)
    validate_goal_schema(result)

    set_cached(
        GOAL_COLLECTION, key,
        {"normalized_prompt": normalize(user_prompt), "goal_json": result},
        embedding=None,
    )
    return {"goal": result, "cache_hit": "none", "tokens_used": usage.get("total_tokens", 0)}


# ── Phase 5 — exact → semantic → LLM ─────────────────────────────────────────

def understand_goal_with_semantic(user_prompt: str) -> dict:
    """
    Full cache chain: exact → semantic → LLM fallback.

    Returns:
        {"goal": dict, "cache_hit": "exact"|"semantic(x.xx)"|"none", "tokens_used": int}
    """
    key = hash_key(user_prompt)

    # 1. Exact cache hit
    cached = get_cached(GOAL_COLLECTION, key)
    if cached:
        return {"goal": cached["goal_json"], "cache_hit": "exact", "tokens_used": 0}

    # 2. Semantic cache hit
    semantic_match, score = semantic_lookup(GOAL_COLLECTION, user_prompt)
    if semantic_match:
        return {
            "goal": semantic_match["goal_json"],
            "cache_hit": f"semantic({score:.2f})",
            "tokens_used": 0,
        }

    # 3. LLM call — local Ollama or Fireworks cloud per LLM_BACKEND
    result, usage = call_llm(LLM_BACKEND, _model(), GOAL_SYSTEM_PROMPT, user_prompt)
    validate_goal_schema(result)

    # Store with embedding so future paraphrases hit the semantic cache
    embedding = get_embedding(normalize(user_prompt))
    set_cached(
        GOAL_COLLECTION, key,
        {"normalized_prompt": normalize(user_prompt), "goal_json": result},
        embedding=embedding,
    )
    return {"goal": result, "cache_hit": "none", "tokens_used": usage.get("total_tokens", 0)}
