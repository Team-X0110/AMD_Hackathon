"""Tier escalation and fallback ladder."""
from __future__ import annotations

from src.routing.models import ESCALATION_LADDER, RouteTier


def next_tier(current: RouteTier) -> RouteTier | None:
    """Move one step up the capability ladder."""
    try:
        idx = ESCALATION_LADDER.index(current)
    except ValueError:
        return None
    if idx + 1 >= len(ESCALATION_LADDER):
        return None
    return ESCALATION_LADDER[idx + 1]


def skip_tier(current: RouteTier) -> RouteTier | None:
    """Skip broken tier on infra failure (e.g. Ollama down)."""
    if current == RouteTier.LOCAL:
        return RouteTier.FIREWORKS_SMALL
    return next_tier(current)


def execution_start_tier(
    decision_tier: RouteTier,
    *,
    agent: str,
    python_confident: bool,
) -> RouteTier:
    """
    Local-first execution: start at local unless python tier is very confident for goal agent.
    """
    if agent == "goal" and decision_tier == RouteTier.PYTHON and python_confident:
        return RouteTier.PYTHON
    return RouteTier.LOCAL
