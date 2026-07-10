"""
pipeline.py — Full orchestration: Goal Understanding → Task Planning.

This is the single entry point for the system. Call run_pipeline(user_prompt)
and get back a structured result including cache hit labels, token cost, and latency.

Phase 5 adds:
  - Semantic cache fallback at both agent levels
  - Firestore logging of every run (for the demo dashboard)
  - Local JSONL mirror in logs/run_logs.jsonl
"""
from __future__ import annotations
import json
import logging
import time
from pathlib import Path
from datetime import datetime, timezone

from src.cache.firestore_client import get_db
from src.agents.goal_understanding import understand_goal_with_semantic
from src.agents.task_planning import plan_tasks_with_semantic
from src.config import RUNS_COLLECTION

# Local log file mirror
LOG_PATH = Path(__file__).parent.parent / "logs" / "run_logs.jsonl"
logger = logging.getLogger(__name__)


# ── Public API ────────────────────────────────────────────────────────────────

def run_pipeline(user_prompt: str) -> dict:
    """
    Run the full Goal Understanding → Task Planning pipeline.

    Returns:
        {
          "goal":            dict,
          "tasks":           dict,
          "cache_hits":      dict,
          "tokens_used":     int,
          "fireworks_tokens": int,
          "latency_sec":     float,
          "routing":         dict,
        }
    """
    t0 = time.perf_counter()

    goal_result = understand_goal_with_semantic(user_prompt)
    plan_result = plan_tasks_with_semantic(goal_result["goal"])

    total_tokens = goal_result["tokens_used"] + plan_result["tokens_used"]
    fireworks_tokens = goal_result.get("fireworks_tokens", 0) + plan_result.get(
        "fireworks_tokens", 0
    )
    latency = round(time.perf_counter() - t0, 3)

    _log_run(
        user_prompt, goal_result, plan_result, total_tokens, fireworks_tokens, latency
    )

    return {
        "goal": goal_result["goal"],
        "tasks": plan_result["tasks"],
        "cache_hits": {
            "goal": goal_result["cache_hit"],
            "plan": plan_result["cache_hit"],
        },
        "tokens_used": total_tokens,
        "fireworks_tokens": fireworks_tokens,
        "latency_sec": latency,
        "routing": {
            "goal": goal_result.get("routing", []),
            "plan": plan_result.get("routing", []),
        },
    }


# ── Logging ───────────────────────────────────────────────────────────────────

def _log_run(
    prompt: str,
    goal_result: dict,
    plan_result: dict,
    tokens: int,
    fireworks_tokens: int,
    latency: float,
) -> None:
    record = {
        "prompt": prompt,
        "goal_cache_hit": goal_result["cache_hit"],
        "plan_cache_hit": plan_result["cache_hit"],
        "tokens_used": tokens,
        "fireworks_tokens": fireworks_tokens,
        "goal_routing": goal_result.get("routing", []),
        "plan_routing": plan_result.get("routing", []),
        "latency_sec": latency,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    # ── Firestore ──────────────────────────────────────────────────────────────
    try:
        get_db().child(RUNS_COLLECTION).push(record)
    except Exception as exc:
        logger.warning("RTDB run log failed: %s", exc)

    # ── Local JSONL ───────────────────────────────────────────────────────────
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")
    except Exception as exc:
        logger.warning("local run log write failed: %s", exc)
