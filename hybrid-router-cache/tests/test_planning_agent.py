"""
tests/test_planning_agent.py — Unit tests for the Task Planning Agent.
"""
from __future__ import annotations

import pytest
from unittest.mock import patch, MagicMock

from src.agents.task_planning import plan_key_from_goal
from src.routing.models import RouteOutcome, RouteTier, TokenUsage

VALID_GOAL = {
    "intent": "build a REST API with authentication",
    "entities": ["REST API", "JWT", "PostgreSQL"],
    "constraints": ["must use JWT"],
    "success_criteria": ["API returns 200 for valid requests"],
    "domain": "software engineering",
    "complexity_hint": "medium",
}

VALID_PLAN = {
    "tasks": [
        {
            "id": "t1",
            "title": "Set up project structure",
            "description": "Initialize repo and install dependencies.",
            "depends_on": [],
            "estimated_effort": "S",
        },
        {
            "id": "t2",
            "title": "Implement JWT auth middleware",
            "description": "Create middleware to validate JWT tokens.",
            "depends_on": ["t1"],
            "estimated_effort": "M",
        },
        {
            "id": "t3",
            "title": "Build user CRUD endpoints",
            "description": "Implement register, login, profile endpoints.",
            "depends_on": ["t2"],
            "estimated_effort": "M",
        },
    ],
    "execution_order": ["t1", "t2", "t3"],
    "parallel_groups": [["t1"], ["t2"], ["t3"]],
}


def _mock_engine(plan=VALID_PLAN, tokens=800, fw_tokens=0):
    engine = MagicMock()
    engine.execute_with_escalation.return_value = (
        plan,
        TokenUsage(local_tokens=tokens, fireworks_tokens=fw_tokens),
        [
            RouteOutcome(
                agent="plan",
                tier=RouteTier.LOCAL,
                success=True,
                local_tokens=tokens,
                fireworks_tokens=fw_tokens,
            )
        ],
    )
    return engine


def test_plan_key_deterministic():
    assert plan_key_from_goal(VALID_GOAL) == plan_key_from_goal(VALID_GOAL)


def test_plan_key_order_invariant():
    goal_reversed = dict(reversed(list(VALID_GOAL.items())))
    assert plan_key_from_goal(VALID_GOAL) == plan_key_from_goal(goal_reversed)


@patch("src.agents.task_planning.set_cached")
@patch("src.agents.task_planning.semantic_lookup", return_value=(None, 0.0))
@patch("src.agents.task_planning.get_cached", return_value=None)
@patch("src.agents.task_planning.get_embedding", return_value=[0.2] * 768)
@patch("src.agents.task_planning.get_routing_engine")
def test_plan_tasks_cache_miss(mock_engine_fn, mock_embed, mock_get, mock_sem, mock_set):
    mock_engine_fn.return_value = _mock_engine()
    from src.agents.task_planning import plan_tasks_with_semantic

    result = plan_tasks_with_semantic(VALID_GOAL)
    assert result["cache_hit"] == "none"
    assert result["tokens_used"] == 800
    assert len(result["tasks"]["tasks"]) == 3
    mock_engine_fn.return_value.execute_with_escalation.assert_called_once()
    mock_set.assert_called_once()


@patch("src.agents.task_planning.set_cached")
@patch("src.agents.task_planning.semantic_lookup", return_value=(None, 0.0))
@patch("src.agents.task_planning.get_embedding", return_value=[0.2] * 768)
@patch("src.agents.task_planning.get_routing_engine")
def test_plan_tasks_exact_cache_hit(mock_engine_fn, mock_embed, mock_sem, mock_set):
    from src.agents.task_planning import plan_tasks_with_semantic

    cached_entry = {"tasks_json": VALID_PLAN}
    with patch("src.agents.task_planning.get_cached", return_value=cached_entry):
        result = plan_tasks_with_semantic(VALID_GOAL)
    assert result["cache_hit"] == "exact"
    assert result["tokens_used"] == 0
    mock_engine_fn.return_value.execute_with_escalation.assert_not_called()


@patch("src.agents.task_planning.set_cached")
@patch("src.agents.task_planning.semantic_lookup", return_value=(None, 0.0))
@patch("src.agents.task_planning.get_cached", return_value=None)
@patch("src.agents.task_planning.get_embedding", return_value=[0.2] * 768)
@patch("src.agents.task_planning.get_routing_engine")
def test_plan_tasks_raises_on_validation_failure(mock_engine_fn, mock_embed, mock_get, mock_sem, mock_set):
    from src.agents.task_planning import plan_tasks_with_semantic

    mock_engine_fn.return_value.execute_with_escalation.side_effect = ValueError(
        "Cycle detected in task dependency graph"
    )
    with pytest.raises(ValueError, match="Cycle detected"):
        plan_tasks_with_semantic(VALID_GOAL)
