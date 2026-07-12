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
from src.agents.prompt_refinement import refine_prompt
from src.agents.response_generation import generate_response
from src.config import RUNS_COLLECTION

# --- NEW ROUTER IMPORTS ---
from src.cache.global_semantic_cache import semantic_lookup as global_semantic_lookup, add_to_local_cache
from src.agents.feature_extractor import FeatureExtractor

# Local log file mirror
LOG_PATH = Path(__file__).parent.parent / "logs" / "run_logs.jsonl"
logger = logging.getLogger(__name__)

# Initialize singletons for the worker lifecycle to avoid overhead
extractor = FeatureExtractor()

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
        # Ensure response_text exists for old cache entries
        if not cached_doc.get("response_text"):
            cached_doc["response_text"] = (
                "*(Answered from semantic cache — zero tokens used.)*"
            )
        return cached_doc

    # ── Phase 2: Feature Extraction ───────────────────────────────────────────
    print("🔍 Cache miss. Extracting features and calculating complexity...")
    features = extractor.extract(user_prompt)
    print(f"📊 Features: {features}")

    # ── Agent 1: Prompt Refinement ────────────────────────────────────────────
    print("📝 Refining user prompt...")
    refinement_result = refine_prompt(user_prompt)
    refined_user_prompt = (
        refinement_result.get("refinement", {}).get("refined_prompt")
        or user_prompt
    )
    print(f"✨ Refined Prompt: {refined_user_prompt}")

    # ── Agent 2: Goal Understanding ───────────────────────────────────────────
    goal_result = understand_goal_with_semantic(refined_user_prompt)

    # ── Agent 3: Task Planning ────────────────────────────────────────────
    plan_result = plan_tasks_with_semantic(goal_result["goal"])

    # ── Agent 4: Response Generation (natural conversational reply) ───────
    print("💬 Generating conversational response...")
    response_result = generate_response(
        refined_user_prompt,
        goal_result["goal"],
        plan_result["tasks"],
    )

    total_tokens = (
        refinement_result["tokens_used"]
        + goal_result["tokens_used"]
        + plan_result["tokens_used"]
        + response_result["tokens_used"]
    )
    fireworks_tokens = (
        refinement_result.get("fireworks_tokens", 0)
        + goal_result.get("fireworks_tokens", 0)
        + plan_result.get("fireworks_tokens", 0)
        + response_result.get("fireworks_tokens", 0)
    )
    latency = round(time.perf_counter() - t0, 3)

    routing_decision = goal_result.get("routing", [{}])[0] if goal_result.get("routing") else {"routed_tier": "LOCAL", "complexity_score": 0}
    tier = routing_decision.get("routed_tier", "LOCAL")
    complexity = routing_decision.get("complexity_score", 0)
    print(f"🧠 Routing Decision: Tier=[{str(tier).upper()}], Complexity=[{complexity}/10]")

    final_response = {
        "response_text": response_result["response"],  # Natural language reply for frontend
        "refined_prompt": refined_user_prompt,
        "goal": goal_result["goal"],
        "tasks": plan_result["tasks"],
        "cache_hits": {
            "goal": goal_result.get("cache_hit", "none"),
            "plan": plan_result.get("cache_hit", "none"),
        },
        "refined_prompt_details": refinement_result["refinement"],
        "routing_metrics": routing_decision, # Send the brain's logic to the frontend!
        "tokens_used": total_tokens,
        "fireworks_tokens": fireworks_tokens,
        "latency_sec": latency,
        "routing": {
            "refinement": refinement_result.get("routing", []),
            "goal": goal_result.get("routing", []),
            "plan": plan_result.get("routing", []),
        },
    }

    # ── Phase 5: Save to Local Memory ─────────────────────────────────────
    add_to_local_cache(user_prompt, final_response)

    # ── Logging ───────────────────────────────────────────────────────────────
    _log_run(user_prompt, refinement_result, goal_result, plan_result, total_tokens, fireworks_tokens, latency)

    return final_response


# ── Logging ───────────────────────────────────────────────────────────────────

def _log_run(
    prompt: str,
    refinement_result: dict,
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
        "refinement_routing": refinement_result.get("routing", []),
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
