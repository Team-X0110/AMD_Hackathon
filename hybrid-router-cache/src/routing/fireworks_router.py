"""Fireworks Function Calling router — select_route tool."""
from __future__ import annotations

import json
import logging

from src.config import FIREWORKS_API_KEY, ROUTER_FC_MODEL, ROUTING_FC_THRESHOLD
from src.fireworks_client import call_fireworks_with_tools
from src.routing.learning import get_stats_summary
from src.routing.models import RouteDecision, RouteTier

logger = logging.getLogger(__name__)

SELECT_ROUTE_TOOL = {
    "type": "function",
    "function": {
        "name": "select_route",
        "description": (
            "Choose the optimal execution backend for an AI agent call. "
            "Prefer local and python tiers to minimize Fireworks tokens."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "tier": {
                    "type": "string",
                    "enum": [t.value for t in RouteTier],
                },
                "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                "reason": {"type": "string"},
                "optimize_for": {
                    "type": "string",
                    "enum": ["tokens", "latency", "accuracy"],
                },
            },
            "required": ["tier", "confidence", "reason"],
        },
    },
}

ROUTER_SYSTEM_PROMPT = """You are a token-efficient model router for a hackathon scoring system.
Only Fireworks API tokens count toward the score — local and python tiers cost zero Fireworks tokens.

Pick the CHEAPEST tier that can still produce accurate structured JSON:
- python: trivial goal extraction only (goal agent, very short prompts)
- local: Ollama on localhost (zero Fireworks tokens) — preferred default
- fireworks_small: gpt-oss-20b — first Fireworks escalation
- fireworks_medium: gpt-oss-120b — planning / medium complexity
- fireworks_large: deepseek-v4-pro — only when simpler tiers likely fail

Always optimize_for tokens unless accuracy is clearly at risk."""


def route_via_fireworks_fc(
    agent: str,
    text: str,
    heuristic_tier: RouteTier,
    heuristic_reason: str,
) -> RouteDecision | None:
    """Call Fireworks FC to pick a route. Returns None when FC is unavailable."""
    if not FIREWORKS_API_KEY:
        return None

    user_payload = {
        "agent": agent,
        "input_preview": text[:2000],
        "heuristic_suggestion": heuristic_tier.value,
        "heuristic_reason": heuristic_reason,
        "learned_stats": get_stats_summary(agent),
        "optimize_for": "tokens",
    }

    messages = [
        {"role": "system", "content": ROUTER_SYSTEM_PROMPT},
        {"role": "user", "content": json.dumps(user_payload)},
    ]

    try:
        tool_args, usage = call_fireworks_with_tools(
            ROUTER_FC_MODEL,
            messages,
            [SELECT_ROUTE_TOOL],
            tool_choice={"type": "function", "function": {"name": "select_route"}},
            temperature=0.1,
        )
        return RouteDecision(
            tier=RouteTier(tool_args["tier"]),
            confidence=float(tool_args.get("confidence", 0.7)),
            reason=tool_args.get("reason", "fireworks_fc"),
            source="fireworks_fc",
            optimize_for=tool_args.get("optimize_for", "tokens"),
            routing_tokens=usage.get("total_tokens", 0),
        )
    except (RuntimeError, ValueError, KeyError, TypeError) as exc:
        logger.warning(
            "Fireworks function-calling router unavailable; falling back to heuristics: %s",
            exc,
        )
        return None


def should_use_fc(confidence: float) -> bool:
    return confidence < ROUTING_FC_THRESHOLD
