"""
eval_router.py — Local eval harness for token-efficient routing.

Reports fireworks token usage (scoring metric) and validation accuracy.

Usage:
    cd hybrid-router-cache
    python eval_router.py
"""
from __future__ import annotations

import json
import sys

from src.validators import validate_goal_schema, validate_task_graph

PROMPTS = [
    "Build a REST API for a todo app with user authentication and JWT tokens",
    "Build a REST API for a todo app with user authentication and JWT tokens",
    "Create a RESTful backend service for task management with login and JWT-based auth",
    "Design a real-time chat application with WebSocket support and message persistence",
    "build a todo api",
]


def _accuracy_check(result: dict) -> bool:
    try:
        validate_goal_schema(result["goal"])
        validate_task_graph(result["tasks"])
        return True
    except ValueError:
        return False


def _route_label(routing: list) -> str:
    if not routing:
        return "cache"
    return routing[-1].get("tier", "unknown")


def main() -> int:
    from src.pipeline import run_pipeline

    print("=" * 72)
    print("  HYBRID ROUTER — Local Eval")
    print("=" * 72)

    total_fireworks = 0
    total_tokens = 0
    accurate = 0
    cache_hits = 0
    route_counts: dict[str, int] = {}
    latencies: list[float] = []

    for i, prompt in enumerate(PROMPTS, 1):
        result = run_pipeline(prompt)
        ok = _accuracy_check(result)
        accurate += int(ok)
        total_fireworks += result.get("fireworks_tokens", 0)
        total_tokens += result["tokens_used"]
        latencies.append(result["latency_sec"])

        goal_hit = result["cache_hits"]["goal"]
        plan_hit = result["cache_hits"]["plan"]
        if goal_hit != "none":
            cache_hits += 1
        if plan_hit != "none":
            cache_hits += 1

        for leg in ("goal", "plan"):
            label = _route_label(result.get("routing", {}).get(leg, []))
            route_counts[label] = route_counts.get(label, 0) + 1

        print(f"\nRun {i}: {prompt[:60]}...")
        print(f"  accurate={ok} fireworks_tokens={result.get('fireworks_tokens', 0)} "
              f"total_tokens={result['tokens_used']} latency={result['latency_sec']:.3f}s")
        print(f"  cache: goal={goal_hit} plan={plan_hit}")

    n = len(PROMPTS)
    print("\n" + "=" * 72)
    print("  SUMMARY")
    print("=" * 72)
    print(f"  Prompts run           : {n}")
    print(f"  Accuracy rate         : {accurate}/{n} ({100 * accurate / n:.0f}%)")
    print(f"  Fireworks tokens total: {total_fireworks}  (primary score proxy)")
    print(f"  Total tokens          : {total_tokens}")
    print(f"  Cache hit legs        : {cache_hits}/{n * 2}")
    print(f"  Avg latency (s)       : {sum(latencies) / n:.3f}")
    print(f"  Route distribution    : {json.dumps(route_counts)}")
    print("=" * 72)

    return 0 if accurate == n else 1


if __name__ == "__main__":
    sys.exit(main())
