"""Routing outcome learning — RTDB + local JSONL mirror."""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path

from src.config import ROUTING_STATS_COLLECTION
from src.routing.models import RouteOutcome, RouteTier

LOG_PATH = Path(__file__).parent.parent.parent / "logs" / "routing_stats.jsonl"
logger = logging.getLogger(__name__)

# In-memory cache when RTDB unavailable (tests, offline)
_memory_stats: dict[str, dict] = {}


def _stats_key(agent: str, tier: RouteTier) -> str:
    return f"{agent}:{tier.value}"


def _default_bucket() -> dict:
    return {
        "attempts": 0,
        "successes": 0,
        "ema_success_rate": 0.85,
        "avg_fireworks_tokens": 0.0,
        "avg_latency_ms": 0.0,
    }


def _get_bucket(agent: str, tier: RouteTier) -> dict:
    key = _stats_key(agent, tier)
    if key not in _memory_stats:
        _memory_stats[key] = _default_bucket()
    return _memory_stats[key]


def record_outcome(outcome: RouteOutcome) -> None:
    """Update EMA stats for (agent, tier)."""
    bucket = _get_bucket(outcome.agent, outcome.tier)
    bucket["attempts"] += 1
    if outcome.success:
        bucket["successes"] += 1

    success_val = 1.0 if outcome.success else 0.0
    bucket["ema_success_rate"] = 0.9 * bucket["ema_success_rate"] + 0.1 * success_val

    n = bucket["attempts"]
    bucket["avg_fireworks_tokens"] += (
        (outcome.fireworks_tokens - bucket["avg_fireworks_tokens"]) / n
    )
    bucket["avg_latency_ms"] += (outcome.latency_ms - bucket["avg_latency_ms"]) / n

    record = {
        "agent": outcome.agent,
        "tier": outcome.tier.value,
        "success": outcome.success,
        "validation_failed": outcome.validation_failed,
        "fireworks_tokens": outcome.fireworks_tokens,
        "local_tokens": outcome.local_tokens,
        "latency_ms": outcome.latency_ms,
        "timestamp": time.time(),
    }

    try:
        from src.cache.firestore_client import get_db

        get_db().child(ROUTING_STATS_COLLECTION).child(
            _stats_key(outcome.agent, outcome.tier).replace(":", "_")
        ).set(bucket)
    except Exception as exc:
        logger.warning("RTDB routing stats write failed: %s", exc)

    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")
    except Exception as exc:
        logger.warning("local routing stats write failed: %s", exc)


def get_stats_summary(agent: str) -> dict[str, dict[str, float]]:
    """Return learned metrics per tier for Fireworks function-calling routing."""
    summary: dict[str, dict[str, float]] = {}
    for tier in RouteTier:
        bucket = _get_bucket(agent, tier)
        summary[_stats_key(agent, tier)] = {
            "ema_success_rate": bucket["ema_success_rate"],
            "avg_fireworks_tokens": bucket["avg_fireworks_tokens"],
            "avg_latency_ms": bucket["avg_latency_ms"],
        }
    return summary


def get_learned_stats_flat(agent: str) -> dict[str, float]:
    return {
        key: metrics["ema_success_rate"]
        for key, metrics in get_stats_summary(agent).items()
    }
