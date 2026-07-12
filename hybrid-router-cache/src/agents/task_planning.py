"""
agents/task_planning.py — Task Planning Agent.

Cache key is based on normalized GOAL JSON.
Uses local-first dynamic routing with validation-gated escalation.
"""
from __future__ import annotations
import json

from src.config import PLAN_COLLECTION
from src.fireworks_client import get_embedding
from src.cache.exact_cache import normalize, hash_key, get_cached, set_cached
from src.cache.semantic_cache import semantic_lookup
from src.integration import build_routing_context, execute_with_reflection
from core.types import TaskType


def plan_key_from_goal(goal: dict) -> str:
    canonical = json.dumps(goal, sort_keys=True)
    return hash_key(canonical)


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


def _run_plan_llm(goal_text: str, goal: dict) -> tuple[dict, int, int, list[dict]]:
    context = build_routing_context(goal_text, PLAN_SYSTEM_PROMPT, TaskType.REASONING, expected_output_format="json")
    outcome = execute_with_reflection(context)
    
    result = outcome["result"]
    total_tokens = outcome["tokens_used"]
    fw_tokens = total_tokens if outcome["routing_metrics"]["routed_tier"] != "LOCAL" else 0
    routing = [outcome["routing_metrics"]]
    
    return result, total_tokens, fw_tokens, routing


def plan_tasks(goal: dict, retry: bool = True) -> dict:
    """Exact cache only."""
    key = plan_key_from_goal(goal)

    cached = get_cached(PLAN_COLLECTION, key)
    if cached:
        return {"tasks": cached["tasks_json"], "cache_hit": "exact", "tokens_used": 0}

    goal_str = json.dumps(goal)
    result, tokens, fw_tokens, routing = _run_plan_llm(goal_str, goal)

    set_cached(PLAN_COLLECTION, key, {"goal_json": goal, "tasks_json": result})
    return {
        "tasks": result,
        "cache_hit": "none",
        "tokens_used": tokens,
        "fireworks_tokens": fw_tokens,
        "routing": routing,
    }


def plan_tasks_with_semantic(goal: dict, retry: bool = True) -> dict:
    """Full cache chain: exact → semantic → routed LLM fallback."""
    key = plan_key_from_goal(goal)

    cached = get_cached(PLAN_COLLECTION, key)
    if cached:
        return {
            "tasks": cached["tasks_json"],
            "cache_hit": "exact",
            "tokens_used": 0,
            "fireworks_tokens": 0,
            "routing": [],
        }

    goal_text = json.dumps(goal, sort_keys=True)
    semantic_match, score = semantic_lookup(PLAN_COLLECTION, goal_text)
    if semantic_match:
        return {
            "tasks": semantic_match["tasks_json"],
            "cache_hit": f"semantic({score:.2f})",
            "tokens_used": 0,
            "fireworks_tokens": 0,
            "routing": [],
        }

    result, tokens, fw_tokens, routing = _run_plan_llm(goal_text, goal)

    embedding = get_embedding(normalize(goal_text))
    set_cached(
        PLAN_COLLECTION, key,
        {"goal_json": goal, "tasks_json": result},
        embedding=embedding,
    )
    return {
        "tasks": result,
        "cache_hit": "none",
        "tokens_used": tokens,
        "fireworks_tokens": fw_tokens,
        "routing": routing,
    }
