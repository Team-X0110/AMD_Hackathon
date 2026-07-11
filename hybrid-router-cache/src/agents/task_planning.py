"""
agents/task_planning.py — Task Planning Agent (Agent 2).

Cache handling has been moved to the top-level Routing Engine in pipeline.py.
This agent receives a dynamically routed model tier, decomposes the goal into 
an actionable dependency graph, and includes self-healing retry logic if 
DAG validation fails.
"""
from __future__ import annotations
import json

from src.config import LOCAL_MODEL, PLAN_MODEL
from src.fireworks_client import call_llm
from src.validators import validate_task_graph


# ── Which model to use per tier ──────────────────────────────────────────────
def _get_model_for_tier(tier: str) -> str:
    """
    Maps the router's tier decision to active Fireworks Serverless models.
    """
    if tier == "local":
        return LOCAL_MODEL
    elif tier in ["small", "medium", "large"]:
        # The powerhouse model your API key has explicit access to
        return "accounts/fireworks/models/deepseek-v4-pro"
    
    # Keep return GOAL_MODEL here (or PLAN_MODEL in task_planning.py)
    return PLAN_MODEL


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


# ── Execution ─────────────────────────────────────────────────────────────────

def plan_tasks_with_semantic(goal: dict, tier: str = "local", retry: bool = True) -> dict:
    """
    Executes the LLM call using the model tier determined by the RoutingEngine.
    Includes an automatic retry if the generated task graph has cyclical dependencies.
    """
    target_model = _get_model_for_tier(tier)
    print(f"[Agent 2] Executing Task Planning on Tier: {tier.upper()} | Model: {target_model}")
    
    goal_text = json.dumps(goal)
    
    # 1. First attempt at DAG generation
    result, usage = call_llm(tier, target_model, PLAN_SYSTEM_PROMPT, goal_text)

    # 2. Validation and Self-Healing
    try:
        validate_task_graph(result)
    except ValueError as e:
        if retry:
            print(f"[Agent 2] DAG Validation failed: {e}. Executing self-healing retry...")
            corrective = (
                goal_text
                + f"\n\nYour previous attempt was invalid: {e}\n"
                "Fix the issues and return corrected JSON."
            )
            # Re-run with the corrective prompt
            result, usage2 = call_llm(tier, target_model, PLAN_SYSTEM_PROMPT, corrective)
            validate_task_graph(result)
            
            # Combine token usage from both attempts
            usage["total_tokens"] = usage.get("total_tokens", 0) + usage2.get("total_tokens", 0)
        else:
            raise

    return {
        "tasks": result,
        "tokens_used": usage.get("total_tokens", 0)
    }