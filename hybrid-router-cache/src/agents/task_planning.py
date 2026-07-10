"""
agents/task_planning.py — Task Planning Agent.

Runs fully locally via Ollama (llama3.1:8b) right now.
To switch to Fireworks cloud: set LLM_BACKEND=fireworks in .env — zero code change.

Key differences from Goal Understanding Agent:
  1. Cache key is based on normalized GOAL JSON, not the raw prompt.
     Two differently-worded prompts that produce the same goal share a plan cache entry.
  2. Validates a dependency graph — checks for unknown deps and cycles (Kahn's algorithm).
  3. Retries once with corrective note if validation fails.
"""
from __future__ import annotations
import json

from src.config import LLM_BACKEND, LOCAL_MODEL, PLAN_MODEL, PLAN_COLLECTION
from src.fireworks_client import call_llm, get_embedding
from src.cache.exact_cache import normalize, hash_key, get_cached, set_cached
from src.cache.semantic_cache import semantic_lookup
from src.validators import validate_task_graph


# ── Which model to use per backend ────────────────────────────────────────────
def _model() -> str:
    return LOCAL_MODEL if LLM_BACKEND == "local" else PLAN_MODEL


# ── Cache key ─────────────────────────────────────────────────────────────────

def plan_key_from_goal(goal: dict) -> str:
    """
    Derive a deterministic cache key from the goal dict.
    sort_keys=True ensures the same goal with different key ordering hashes identically.
    """
    canonical = json.dumps(goal, sort_keys=True)
    return hash_key(canonical)


# ── System prompt ─────────────────────────────────────────────────────────────
PLAN_SYSTEM_PROMPT = """You are a Task Planning Agent. Given a structured goal JSON, decompose it into an actionable task graph.

Return a JSON object with EXACTLY these top-level keys:

{
  "tasks": [
    {
      "id": "t1",
      "title": "<short action title>",
      "description": "<1-2 sentence explanation>",
      "depends_on": [],
      "estimated_effort": "<one of: S | M | L | XL>"
    }
  ],
  "execution_order": ["t1", "t2"],
  "parallel_groups": [["t2", "t3"], ["t4"]]
}

Rules:
- Output ONLY valid JSON. No prose, no markdown fences.
- Every task must have a unique 'id' (t1, t2, ... tn).
- 'depends_on' lists IDs of tasks that must complete BEFORE this one starts.
- 'depends_on' must only reference IDs that exist in 'tasks'. No undefined IDs.
- The dependency graph MUST be acyclic (no task can depend on itself, directly or transitively).
- Maximum 15 tasks total. Consolidate related steps if needed.
- 'execution_order' is a flat topological ordering.
- 'parallel_groups' shows tasks safe to run concurrently.
- 'estimated_effort': S=hours, M=1-2 days, L=3-5 days, XL=week+"""


# ── Phase 4 — exact cache only ────────────────────────────────────────────────

def plan_tasks(goal: dict, retry: bool = True) -> dict:
    """
    Exact cache only. Use plan_tasks_with_semantic for the full pipeline.

    Returns:
        {"tasks": dict, "cache_hit": "exact"|"none", "tokens_used": int}
    """
    key = plan_key_from_goal(goal)

    cached = get_cached(PLAN_COLLECTION, key)
    if cached:
        return {"tasks": cached["tasks_json"], "cache_hit": "exact", "tokens_used": 0}

    goal_str = json.dumps(goal)
    result, usage = call_llm(LLM_BACKEND, _model(), PLAN_SYSTEM_PROMPT, goal_str)

    try:
        validate_task_graph(result)
    except ValueError as e:
        if retry:
            corrective = (
                goal_str
                + f"\n\nYour previous attempt was invalid: {e}\n"
                "Fix the issues and return corrected JSON."
            )
            result, usage2 = call_llm(LLM_BACKEND, _model(), PLAN_SYSTEM_PROMPT, corrective)
            validate_task_graph(result)
            usage["total_tokens"] = (
                usage.get("total_tokens", 0) + usage2.get("total_tokens", 0)
            )
        else:
            raise

    set_cached(PLAN_COLLECTION, key, {"goal_json": goal, "tasks_json": result})
    return {"tasks": result, "cache_hit": "none", "tokens_used": usage.get("total_tokens", 0)}


# ── Phase 5 — exact → semantic → LLM ─────────────────────────────────────────

def plan_tasks_with_semantic(goal: dict, retry: bool = True) -> dict:
    """
    Full cache chain: exact → semantic → LLM fallback.

    Returns:
        {"tasks": dict, "cache_hit": "exact"|"semantic(x.xx)"|"none", "tokens_used": int}
    """
    key = plan_key_from_goal(goal)

    # 1. Exact cache hit
    cached = get_cached(PLAN_COLLECTION, key)
    if cached:
        return {"tasks": cached["tasks_json"], "cache_hit": "exact", "tokens_used": 0}

    # 2. Semantic cache hit
    goal_text = json.dumps(goal, sort_keys=True)
    semantic_match, score = semantic_lookup(PLAN_COLLECTION, goal_text)
    if semantic_match:
        return {
            "tasks": semantic_match["tasks_json"],
            "cache_hit": f"semantic({score:.2f})",
            "tokens_used": 0,
        }

    # 3. LLM call — local Ollama or Fireworks cloud per LLM_BACKEND
    result, usage = call_llm(LLM_BACKEND, _model(), PLAN_SYSTEM_PROMPT, goal_text)

    try:
        validate_task_graph(result)
    except ValueError as e:
        if retry:
            corrective = (
                goal_text
                + f"\n\nYour previous attempt was invalid: {e}\n"
                "Fix the issues and return corrected JSON."
            )
            result, usage2 = call_llm(LLM_BACKEND, _model(), PLAN_SYSTEM_PROMPT, corrective)
            validate_task_graph(result)
            usage["total_tokens"] = (
                usage.get("total_tokens", 0) + usage2.get("total_tokens", 0)
            )
        else:
            raise

    # Store with embedding for semantic lookup
    embedding = get_embedding(normalize(goal_text))
    set_cached(
        PLAN_COLLECTION, key,
        {"goal_json": goal, "tasks_json": result},
        embedding=embedding,
    )
    return {"tasks": result, "cache_hit": "none", "tokens_used": usage.get("total_tokens", 0)}
