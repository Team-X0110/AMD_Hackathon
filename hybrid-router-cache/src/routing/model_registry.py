"""Fireworks model metadata for cost-aware routing decisions."""
from __future__ import annotations

from dataclasses import dataclass

from src.routing.models import RouteTier


@dataclass(frozen=True)
class ModelSpec:
    model_id: str
    tier: RouteTier
    input_cost_per_1m: float
    cached_input_cost_per_1m: float
    output_cost_per_1m: float
    context_window: int
    supports_tools: bool
    use_cases: tuple[str, ...]


MODEL_REGISTRY: dict[RouteTier, ModelSpec] = {
    RouteTier.FIREWORKS_SMALL: ModelSpec(
        model_id="accounts/fireworks/models/gpt-oss-20b",
        tier=RouteTier.FIREWORKS_SMALL,
        input_cost_per_1m=0.07,
        cached_input_cost_per_1m=0.035,
        output_cost_per_1m=0.30,
        context_window=131_072,
        supports_tools=True,
        use_cases=("fast extraction", "classification", "search"),
    ),
    RouteTier.FIREWORKS_MEDIUM: ModelSpec(
        model_id="accounts/fireworks/models/gpt-oss-120b",
        tier=RouteTier.FIREWORKS_MEDIUM,
        input_cost_per_1m=0.15,
        cached_input_cost_per_1m=0.015,
        output_cost_per_1m=0.60,
        context_window=131_072,
        supports_tools=True,
        use_cases=("general reasoning", "planning"),
    ),
    RouteTier.FIREWORKS_LARGE: ModelSpec(
        model_id="accounts/fireworks/models/deepseek-v4-pro",
        tier=RouteTier.FIREWORKS_LARGE,
        input_cost_per_1m=1.74,
        cached_input_cost_per_1m=0.145,
        output_cost_per_1m=3.48,
        context_window=1_000_000,
        supports_tools=True,
        use_cases=("agentic", "complex planning", "code"),
    ),
}

ROUTER_FC_SPEC = MODEL_REGISTRY[RouteTier.FIREWORKS_SMALL]


def get_model_spec(tier: RouteTier) -> ModelSpec | None:
    return MODEL_REGISTRY.get(tier)


def estimate_fireworks_cost(
    spec: ModelSpec,
    prompt_tokens: int,
    output_tokens: int,
    *,
    cached_prompt_tokens: int = 0,
) -> float:
    """Estimate USD cost for a Fireworks call (for routing comparisons)."""
    fresh_input = max(0, prompt_tokens - cached_prompt_tokens)
    input_cost = (fresh_input * spec.input_cost_per_1m + cached_prompt_tokens * spec.cached_input_cost_per_1m) / 1_000_000
    output_cost = output_tokens * spec.output_cost_per_1m / 1_000_000
    return input_cost + output_cost


def cheapest_sufficient_tier(
    agent: str,
    complexity: float,
    learned_stats: dict[str, float] | None = None,
) -> RouteTier:
    """
    Pick the cheapest tier likely to succeed given complexity and learned stats.

    complexity: 0.0 (trivial) → 1.0 (very complex)
    """
    stats = learned_stats or {}

    def tier_success_rate(tier: RouteTier) -> float:
        return stats.get(f"{agent}:{tier.value}", 0.85)

    if agent == "goal" and complexity < 0.2 and tier_success_rate(RouteTier.PYTHON) >= 0.85:
        return RouteTier.PYTHON

    if complexity < 0.5:
        return RouteTier.LOCAL

    if complexity < 0.75 and tier_success_rate(RouteTier.FIREWORKS_SMALL) >= 0.80:
        return RouteTier.FIREWORKS_SMALL

    if complexity < 0.9 and tier_success_rate(RouteTier.FIREWORKS_MEDIUM) >= 0.80:
        return RouteTier.FIREWORKS_MEDIUM

    return RouteTier.FIREWORKS_LARGE
