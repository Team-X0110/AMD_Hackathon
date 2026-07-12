"""
tests/test_routing_engine.py — Unit tests for the dynamic routing engine.

Run:
    python -m pytest tests/test_routing_engine.py -v
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.routing.escalation import execution_start_tier, next_tier, skip_tier
from src.routing.heuristics import score_complexity
from src.routing.models import RouteDecision, RouteTier, TokenUsage
from src.routing.python_executor import extract_goal_from_prompt


def test_heuristic_routes_short_goal_to_python():
    tier, conf, reason, _ = score_complexity("build a todo api", "goal")
    assert tier == RouteTier.PYTHON
    assert conf >= 0.85
    assert "short" in reason.lower() or tier == RouteTier.PYTHON


def test_heuristic_plan_never_python():
    tier, _, _, _ = score_complexity("build a todo api", "plan")
    assert tier != RouteTier.PYTHON


def test_execution_start_local_first():
    start = execution_start_tier(
        RouteTier.FIREWORKS_MEDIUM,
        agent="plan",
        python_confident=False,
    )
    assert start == RouteTier.LOCAL


def test_execution_start_python_when_confident():
    start = execution_start_tier(
        RouteTier.PYTHON,
        agent="goal",
        python_confident=True,
    )
    assert start == RouteTier.PYTHON


def test_escalation_ladder():
    assert next_tier(RouteTier.LOCAL) == RouteTier.FIREWORKS_SMALL
    assert next_tier(RouteTier.FIREWORKS_SMALL) == RouteTier.FIREWORKS_MEDIUM
    assert skip_tier(RouteTier.LOCAL) == RouteTier.FIREWORKS_SMALL


def test_python_executor_simple_prompt():
    goal = extract_goal_from_prompt("build a todo api")
    assert goal["complexity_hint"] in {"low", "medium"}
    assert goal["intent"]


def test_python_executor_rejects_long_prompt():
    long_prompt = " ".join(["word"] * 15)
    with pytest.raises(ValueError):
        extract_goal_from_prompt(long_prompt)


VALID_GOAL = {
    "intent": "build an API",
    "entities": ["API"],
    "constraints": [],
    "success_criteria": ["API works"],
    "domain": "software engineering",
    "complexity_hint": "low",
}


@patch("src.routing.engine.route_via_fireworks_fc", return_value=None)
@patch("src.routing.engine.record_outcome")
@patch("src.routing.engine.call_llm")
def test_engine_local_first_success(mock_llm, mock_record, mock_fc):
    mock_llm.return_value = (VALID_GOAL, {"total_tokens": 100, "backend": "local"})
    from src.routing.engine import DynamicRoutingEngine
    from src.validators import validate_goal_schema

    engine = DynamicRoutingEngine()
    result, usage, outcomes = engine.execute_with_escalation(
        agent="goal",
        text="build a moderately complex REST API with authentication",
        system_prompt="sys",
        user_prompt="build a moderately complex REST API with authentication",
        validate_fn=validate_goal_schema,
    )
    assert result == VALID_GOAL
    assert usage.local_tokens == 100
    assert usage.fireworks_tokens == 0
    assert outcomes[0].tier == RouteTier.LOCAL
    mock_llm.assert_called_once()


@patch("src.routing.engine.route_via_fireworks_fc", return_value=None)
@patch("src.routing.engine.record_outcome")
@patch("src.routing.engine.call_llm")
@patch("src.routing.engine.FIREWORKS_API_KEY", "test-key")
def test_engine_escalates_on_validation_failure(mock_llm, mock_record, mock_fc):
    bad = {"intent": "missing keys"}
    mock_llm.side_effect = [
        (bad, {"total_tokens": 50, "backend": "local"}),
        (VALID_GOAL, {"total_tokens": 80, "backend": "fireworks"}),
    ]
    from src.routing.engine import DynamicRoutingEngine
    from src.validators import validate_goal_schema

    engine = DynamicRoutingEngine()
    result, usage, outcomes = engine.execute_with_escalation(
        agent="goal",
        text="build a moderately complex REST API with authentication",
        system_prompt="sys",
        user_prompt="build a moderately complex REST API with authentication",
        validate_fn=validate_goal_schema,
    )
    assert result == VALID_GOAL
    assert mock_llm.call_count == 2
    assert outcomes[-1].tier == RouteTier.FIREWORKS_SMALL
    assert usage.local_tokens == 50
    assert usage.fireworks_tokens == 80


@patch("src.routing.engine.record_outcome")
@patch("src.routing.engine.call_llm")
@patch("src.routing.engine.FIREWORKS_API_KEY", "test-key")
def test_engine_honors_fireworks_fc_decision(mock_llm, mock_record):
    mock_llm.return_value = (VALID_GOAL, {"total_tokens": 120, "backend": "fireworks"})
    from src.routing.engine import DynamicRoutingEngine
    from src.validators import validate_goal_schema

    engine = DynamicRoutingEngine()
    engine.decide = MagicMock(
        return_value=RouteDecision(
            tier=RouteTier.FIREWORKS_MEDIUM,
            confidence=0.91,
            reason="accuracy risk",
            source="fireworks_fc",
            optimize_for="accuracy",
            routing_tokens=12,
        )
    )

    result, usage, outcomes = engine.execute_with_escalation(
        agent="goal",
        text="hard prompt",
        system_prompt="sys",
        user_prompt="hard prompt",
        validate_fn=validate_goal_schema,
    )

    assert result == VALID_GOAL
    assert outcomes[0].tier == RouteTier.FIREWORKS_MEDIUM
    assert usage.fireworks_tokens == 120
    assert usage.routing_tokens == 12


@patch("src.routing.fireworks_router.route_via_fireworks_fc")
def test_fc_only_when_low_confidence(mock_fc):
    from src.routing.fireworks_router import should_use_fc

    assert should_use_fc(0.5) is True
    assert should_use_fc(0.90) is False


def test_token_usage_total():
    usage = TokenUsage(fireworks_tokens=10, local_tokens=20, routing_tokens=5)
    assert usage.total_tokens == 35
