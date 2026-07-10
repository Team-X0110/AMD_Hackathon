"""Zero-token Python heuristics for route selection."""
from __future__ import annotations

import re

from src.routing.model_registry import cheapest_sufficient_tier
from src.routing.models import RouteTier

COMPLEXITY_KEYWORDS = frozenset({
    "microservice", "microservices", "distributed", "kubernetes", "k8s",
    "real-time", "realtime", "websocket", "ml pipeline", "machine learning",
    "authentication", "multi-tenant", "scalable", "event-driven",
})

DOMAIN_KEYWORDS: dict[str, str] = {
    "api": "software engineering",
    "rest": "software engineering",
    "database": "software engineering",
    "frontend": "software engineering",
    "backend": "software engineering",
    "devops": "devops",
    "data": "data analysis",
    "chat": "software engineering",
    "todo": "software engineering",
}


def _word_count(text: str) -> int:
    return len(text.split())


def _complexity_score(text: str, agent: str) -> float:
    lower = text.lower()
    words = _word_count(text)
    score = min(words / 100.0, 0.4)

    if agent == "plan":
        score += 0.25

    hits = sum(1 for kw in COMPLEXITY_KEYWORDS if kw in lower)
    score += min(hits * 0.12, 0.45)

    if re.search(r"\b(and|with|using|including)\b", lower):
        score += 0.05

    return min(score, 1.0)


def score_complexity(
    text: str,
    agent: str,
    learned_stats: dict[str, float] | None = None,
) -> tuple[RouteTier, float, str, float]:
    """
    Returns (suggested_tier, confidence, reason, complexity_score).
    """
    words = _word_count(text)
    complexity = _complexity_score(text, agent)
    lower = text.lower()
    has_complex_kw = any(kw in lower for kw in COMPLEXITY_KEYWORDS)

    if agent == "goal" and words <= 12 and not has_complex_kw:
        return RouteTier.PYTHON, 0.90, "short simple goal prompt", complexity

    if agent == "goal" and words <= 30 and not has_complex_kw:
        return RouteTier.LOCAL, 0.88, "moderate goal — local-first", complexity

    if agent == "plan" or has_complex_kw or words > 80:
        tier = cheapest_sufficient_tier(agent, complexity, learned_stats)
        if tier == RouteTier.LOCAL:
            return tier, 0.72, "complex task — local-first with lower confidence", complexity
        return tier, 0.87, "complex planning task", complexity

    return RouteTier.LOCAL, 0.85, "default local-first", complexity
