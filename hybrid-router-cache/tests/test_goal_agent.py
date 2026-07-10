"""
tests/test_goal_agent.py — Unit tests for the Goal Understanding Agent.
"""
from __future__ import annotations

import pytest
from unittest.mock import patch, MagicMock

from src.routing.models import RouteOutcome, RouteTier, TokenUsage

VALID_GOAL = {
    "intent": "build a REST API with authentication",
    "entities": ["REST API", "authentication", "user management"],
    "constraints": ["must use JWT", "PostgreSQL backend"],
    "success_criteria": ["API returns 200 for valid requests", "invalid tokens get 401"],
    "domain": "software engineering",
    "complexity_hint": "medium",
}


def _mock_engine(goal=VALID_GOAL, tokens=350, fw_tokens=0):
    engine = MagicMock()
    engine.execute_with_escalation.return_value = (
        goal,
        TokenUsage(local_tokens=tokens, fireworks_tokens=fw_tokens),
        [
            RouteOutcome(
                agent="goal",
                tier=RouteTier.LOCAL,
                success=True,
                local_tokens=tokens,
                fireworks_tokens=fw_tokens,
            )
        ],
    )
    return engine


@patch("src.agents.goal_understanding.set_cached")
@patch("src.agents.goal_understanding.semantic_lookup", return_value=(None, 0.0))
@patch("src.agents.goal_understanding.get_cached", return_value=None)
@patch("src.agents.goal_understanding.get_embedding", return_value=[0.1] * 768)
@patch("src.agents.goal_understanding.get_routing_engine")
def test_understand_goal_cache_miss(mock_engine_fn, mock_embed, mock_get, mock_sem, mock_set):
    mock_engine_fn.return_value = _mock_engine()
    from src.agents.goal_understanding import understand_goal_with_semantic

    result = understand_goal_with_semantic("build me a REST API")
    assert result["cache_hit"] == "none"
    assert result["tokens_used"] == 350
    assert result["fireworks_tokens"] == 0
    mock_engine_fn.return_value.execute_with_escalation.assert_called_once()
    mock_set.assert_called_once()


@patch("src.agents.goal_understanding.set_cached")
@patch("src.agents.goal_understanding.semantic_lookup", return_value=(None, 0.0))
@patch("src.agents.goal_understanding.get_embedding", return_value=[0.1] * 768)
@patch("src.agents.goal_understanding.get_routing_engine")
def test_understand_goal_exact_cache_hit(mock_engine_fn, mock_embed, mock_sem, mock_set):
    from src.agents.goal_understanding import understand_goal_with_semantic

    cached_entry = {"goal_json": VALID_GOAL}
    with patch("src.agents.goal_understanding.get_cached", return_value=cached_entry):
        result = understand_goal_with_semantic("build me a REST API")
    assert result["cache_hit"] == "exact"
    assert result["tokens_used"] == 0
    mock_engine_fn.return_value.execute_with_escalation.assert_not_called()


@patch("src.agents.goal_understanding.set_cached")
@patch("src.agents.goal_understanding.semantic_lookup", return_value=(None, 0.0))
@patch("src.agents.goal_understanding.get_cached", return_value=None)
@patch("src.agents.goal_understanding.get_embedding", return_value=[0.1] * 768)
@patch("src.agents.goal_understanding.get_routing_engine")
def test_understand_goal_invalid_schema_raises(mock_engine_fn, mock_embed, mock_get, mock_sem, mock_set):
    from src.agents.goal_understanding import understand_goal_with_semantic

    mock_engine_fn.return_value.execute_with_escalation.side_effect = ValueError(
        "Goal JSON missing required keys"
    )
    with pytest.raises(ValueError, match="missing required keys"):
        understand_goal_with_semantic("schema_validation_test")


@patch("src.agents.goal_understanding.set_cached")
@patch("src.agents.goal_understanding.semantic_lookup", return_value=(None, 0.0))
@patch("src.agents.goal_understanding.get_cached", return_value=None)
@patch("src.agents.goal_understanding.get_embedding", return_value=[0.1] * 768)
@patch("src.agents.goal_understanding.get_routing_engine")
def test_understand_goal_bad_complexity_hint_raises(mock_engine_fn, mock_embed, mock_get, mock_sem, mock_set):
    from src.agents.goal_understanding import understand_goal_with_semantic

    mock_engine_fn.return_value.execute_with_escalation.side_effect = ValueError(
        "Invalid complexity_hint 'extreme'"
    )
    with pytest.raises(ValueError, match="Invalid complexity_hint"):
        understand_goal_with_semantic("bad_complexity_test")
