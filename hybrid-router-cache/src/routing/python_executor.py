"""Rule-based goal extraction for trivial prompts (zero LLM tokens)."""
from __future__ import annotations

import re

from src.routing.heuristics import DOMAIN_KEYWORDS
from src.validators import validate_goal_schema


def extract_goal_from_prompt(user_prompt: str) -> dict:
    """
    Template-based goal JSON for very simple prompts.
    Raises ValueError if the prompt is too complex for rules.
    """
    text = user_prompt.strip()
    words = text.split()
    if len(words) > 12:
        raise ValueError("Prompt too long for python extraction")

    lower = text.lower()

    intent_match = re.search(
        r"\b(build|create|design|implement|make|develop|write)\b\s+(.+)",
        lower,
        re.I,
    )
    if intent_match:
        intent = f"{intent_match.group(1)} {intent_match.group(2).strip()}"
    else:
        intent = text[:80]

    entities: list[str] = []
    for token in re.findall(r"\b[A-Z][a-zA-Z0-9+\.#]*\b|\b[a-z]{3,}\b", text):
        if token.lower() in {"build", "create", "design", "make", "the", "and", "for", "with", "using"}:
            continue
        if len(entities) < 5 and token not in entities:
            entities.append(token)

    domain = "software engineering"
    for kw, dom in DOMAIN_KEYWORDS.items():
        if kw in lower:
            domain = dom
            break

    constraints: list[str] = []
    if "jwt" in lower or "auth" in lower:
        constraints.append("authentication required")
    if "postgres" in lower or "mongodb" in lower or "database" in lower:
        constraints.append("database persistence")

    complexity_hint = "low"
    if len(words) > 8 or len(constraints) > 1:
        complexity_hint = "medium"

    goal = {
        "intent": intent[:120],
        "entities": entities[:5],
        "constraints": constraints,
        "success_criteria": [f"Successfully {intent_match.group(1) if intent_match else 'complete'} the requested work"],
        "domain": domain,
        "complexity_hint": complexity_hint,
    }

    validate_goal_schema(goal)
    return goal
