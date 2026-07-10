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
import time
from pathlib import Path
from datetime import datetime, timezone

from firebase_admin import firestore as fs

from src.cache.firestore_client import get_db
from src.agents.goal_understanding import understand_goal_with_semantic
from src.agents.task_planning import plan_tasks_with_semantic
from src.config import RUNS_COLLECTION

# Local log file mirror
LOG_PATH = Path(__file__).parent.parent / "logs" / "run_logs.jsonl"


# ── Public API ────────────────────────────────────────────────────────────────

def run_pipeline(user_prompt: str) -> dict:
    """
    Run the full Goal Understanding → Task Planning pipeline.

    Returns:
        {
          "goal":        dict,   # structured goal JSON
          "tasks":       dict,   # structured plan JSON
          "cache_hits":  dict,   # {"goal": "exact|semantic(x)|none", "plan": ...}
          "tokens_used": int,    # 0 if both cache hits
          "latency_sec": float,
        }
    """
    t0 = time.perf_counter()

    # ── Agent 1: Goal Understanding ───────────────────────────────────────────
    goal_result = understand_goal_with_semantic(user_prompt)

    # ── Agent 2: Task Planning ────────────────────────────────────────────────
    plan_result = plan_tasks_with_semantic(goal_result["goal"])

    # ── Metrics ───────────────────────────────────────────────────────────────
    total_tokens = goal_result["tokens_used"] + plan_result["tokens_used"]
    latency = round(time.perf_counter() - t0, 3)

    # ── Logging ───────────────────────────────────────────────────────────────
    _log_run(user_prompt, goal_result, plan_result, total_tokens, latency)

    return {
        "goal": goal_result["goal"],
        "tasks": plan_result["tasks"],
        "cache_hits": {
            "goal": goal_result["cache_hit"],
            "plan": plan_result["cache_hit"],
        },
        "tokens_used": total_tokens,
        "latency_sec": latency,
    }


# ── Logging ───────────────────────────────────────────────────────────────────

def _log_run(
    prompt: str,
    goal_result: dict,
    plan_result: dict,
    tokens: int,
    latency: float,
) -> None:
    """
    Log a pipeline run to both Firestore (for dashboard) and a local JSONL file.
    Local file acts as a fallback if Firestore is unavailable.
    """
    record = {
        "prompt": prompt,
        "goal_cache_hit": goal_result["cache_hit"],
        "plan_cache_hit": plan_result["cache_hit"],
        "tokens_used": tokens,
        "latency_sec": latency,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    # ── Firestore ──────────────────────────────────────────────────────────────
    try:
        firestore_record = {**record, "timestamp": fs.SERVER_TIMESTAMP}
        get_db().collection(RUNS_COLLECTION).add(firestore_record)
    except Exception as exc:
        print(f"[pipeline] Warning: Firestore log failed: {exc}")

    # ── Local JSONL ───────────────────────────────────────────────────────────
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")
    except Exception as exc:
        print(f"[pipeline] Warning: local log write failed: {exc}")
