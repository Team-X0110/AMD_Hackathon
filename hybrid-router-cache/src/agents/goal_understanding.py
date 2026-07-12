"""
agents/goal_understanding.py — Goal Understanding Agent.

Cache layers (exact → semantic → routed LLM):
  1. Exact cache  — SHA-256 hash match → 0 tokens, instant
  2. Semantic     — cosine similarity on embeddings → 0 tokens
  3. Routed LLM   — local-first dynamic routing with escalation
"""
from __future__ import annotations

from src.config import GOAL_COLLECTION
from src.fireworks_client import get_embedding
from src.cache.exact_cache import normalize, hash_key, get_cached, set_cached
from src.cache.semantic_cache import semantic_lookup
from src.integration import build_routing_context, execute_with_reflection
from core.types import TaskType


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


def _run_goal_llm(user_prompt: str) -> tuple[dict, int, int, list[dict]]:
    """Execute routed LLM call. Returns goal, tokens_used, fireworks_tokens, routing."""
    context = build_routing_context(user_prompt, GOAL_SYSTEM_PROMPT, TaskType.EXTRACTION, expected_output_format="json")
    outcome = execute_with_reflection(context)
    
    result = outcome["result"]
    total_tokens = outcome["tokens_used"]
    fw_tokens = total_tokens if outcome["routing_metrics"]["routed_tier"] != "LOCAL" else 0
    routing = [outcome["routing_metrics"]]
    
    return result, total_tokens, fw_tokens, routing


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

    result, tokens, fw_tokens, routing = _run_goal_llm(user_prompt)

    set_cached(
        GOAL_COLLECTION, key,
        {"normalized_prompt": normalize(user_prompt), "goal_json": result},
        embedding=None,
    )
    return {
        "goal": result,
        "cache_hit": "none",
        "tokens_used": tokens,
        "fireworks_tokens": fw_tokens,
        "routing": routing,
    }


def understand_goal_with_semantic(user_prompt: str) -> dict:
    """
    Full cache chain: exact → semantic → routed LLM fallback.

    Returns:
        {"goal": dict, "cache_hit": str, "tokens_used": int, "fireworks_tokens": int, "routing": list}
    """
    key = hash_key(user_prompt)

    cached = get_cached(GOAL_COLLECTION, key)
    if cached:
        return {
            "goal": cached["goal_json"],
            "cache_hit": "exact",
            "tokens_used": 0,
            "fireworks_tokens": 0,
            "routing": [],
        }

    semantic_match, score = semantic_lookup(GOAL_COLLECTION, user_prompt)
    if semantic_match:
        return {
            "goal": semantic_match["goal_json"],
            "cache_hit": f"semantic({score:.2f})",
            "tokens_used": 0,
            "fireworks_tokens": 0,
            "routing": [],
        }

    result, tokens, fw_tokens, routing = _run_goal_llm(user_prompt)

    embedding = get_embedding(normalize(user_prompt))
    set_cached(
        GOAL_COLLECTION, key,
        {"normalized_prompt": normalize(user_prompt), "goal_json": result},
        embedding=embedding,
    )
    return {
        "goal": result,
        "cache_hit": "none",
        "tokens_used": tokens,
        "fireworks_tokens": fw_tokens,
        "routing": routing,
    }
