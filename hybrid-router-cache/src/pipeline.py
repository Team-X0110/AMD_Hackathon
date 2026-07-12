"""
pipeline.py — Full orchestration: Goal Understanding → Task Planning.

This is the single entry point for the system. Call run_pipeline(user_prompt)
and get back a structured result including cache hit labels, token cost, and latency.
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

# --- NEW ROUTER IMPORTS ---
from src.cache.global_semantic_cache import semantic_lookup as global_semantic_lookup, add_to_local_cache
from src.agents.feature_extractor import FeatureExtractor
from src.agents.routing_engine import RoutingEngine

# Local log file mirror
LOG_PATH = Path(__file__).parent.parent / "logs" / "run_logs.jsonl"
logger = logging.getLogger(__name__)

# Initialize singletons for the worker lifecycle to avoid overhead
extractor = FeatureExtractor()
router = RoutingEngine()

# ── Public API ────────────────────────────────────────────────────────────────

def run_pipeline(user_prompt: str) -> dict:
    """
    Run the full Goal Understanding → Task Planning pipeline.
    """
    t0 = time.perf_counter()

    # ── Phase 1: Local O(1) Semantic Cache Check ──────────────────────────────
    cached_doc, score = global_semantic_lookup(user_prompt)
    if cached_doc:
        print(f"⚡ Cache Hit! Semantic Score: {score:.3f}. Cost: 0 tokens.")
        # Ensure the frontend gets the metrics it expects
        cached_doc["cache_hits"] = {"goal": f"semantic({score:.2f})", "plan": "semantic"}
        cached_doc["tokens_used"] = 0
        cached_doc["latency_sec"] = round(time.perf_counter() - t0, 3)
        return cached_doc

    # ── Phase 2: Feature Extraction ───────────────────────────────────────────
    print("🔍 Cache miss. Extracting features and calculating complexity...")
    features = extractor.extract(user_prompt)
    routing_decision = router.evaluate(features)

    tier = routing_decision["routed_tier"]
    complexity = routing_decision["complexity_score"]
    print(f"📊 Features: {features}")
    print(f"🧠 Routing Decision: Tier=[{tier.upper()}], Complexity=[{complexity}/10]")

    # ── Agent 1: Goal Understanding ───────────────────────────────────────────
    goal_result = understand_goal_with_semantic(user_prompt)

    # ── Agent 2: Task Planning ────────────────────────────────────────────────
    plan_result = plan_tasks_with_semantic(goal_result["goal"])

    total_tokens = goal_result["tokens_used"] + plan_result["tokens_used"]
    fireworks_tokens = goal_result.get("fireworks_tokens", 0) + plan_result.get(
        "fireworks_tokens", 0
    )
    latency = round(time.perf_counter() - t0, 3)

    final_response = {
        "goal": goal_result["goal"],
        "tasks": plan_result["tasks"],
        "cache_hits": {
            "goal": goal_result.get("cache_hit", "none"),
            "plan": plan_result.get("cache_hit", "none"),
        },
        "routing_metrics": routing_decision, # Send the brain's logic to the frontend!
        "tokens_used": total_tokens,
        "fireworks_tokens": fireworks_tokens,
        "latency_sec": latency,
        "routing": {
            "goal": goal_result.get("routing", []),
            "plan": plan_result.get("routing", []),
        },
    }

    # ── Phase 4: Save to Local Memory ─────────────────────────────────────────
    add_to_local_cache(user_prompt, final_response)

    # ── Logging ───────────────────────────────────────────────────────────────
    _log_run(user_prompt, goal_result, plan_result, total_tokens, fireworks_tokens, latency)

    return final_response


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
        "goal_cache_hit": goal_result.get("cache_hit", "none"),
        "plan_cache_hit": plan_result.get("cache_hit", "none"),
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
