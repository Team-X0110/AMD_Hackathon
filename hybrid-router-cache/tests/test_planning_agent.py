"""
tests/test_planning_agent.py — Unit tests for the Task Planning Agent.

Strategy:
  - Mock call_llm, get_cached, set_cached, and semantic_lookup at the agent boundary.
  - No real DB calls in these tests — fully deterministic.

Run:
    python -m pytest tests/test_planning_agent.py -v
"""
from __future__ import annotations
import pytest
from unittest.mock import patch, MagicMock

from src.agents.task_planning import plan_key_from_goal

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

MOCK_USAGE = {"total_tokens": 800, "prompt_tokens": 500, "completion_tokens": 300}


# ── plan_key_from_goal ────────────────────────────────────────────────────────

def test_plan_key_deterministic():
    assert plan_key_from_goal(VALID_GOAL) == plan_key_from_goal(VALID_GOAL)


def test_plan_key_order_invariant():
    """Dict with keys in different order should produce the same key (sort_keys=True)."""
    import json
    goal_reversed = dict(reversed(list(VALID_GOAL.items())))
    assert plan_key_from_goal(VALID_GOAL) == plan_key_from_goal(goal_reversed)


# ── Happy path ────────────────────────────────────────────────────────────────

@patch("src.agents.task_planning.set_cached")
@patch("src.agents.task_planning.semantic_lookup", return_value=(None, 0.0))
@patch("src.agents.task_planning.get_cached", return_value=None)
@patch("src.agents.task_planning.get_embedding", return_value=[0.2] * 768)
@patch("src.agents.task_planning.call_llm", return_value=(VALID_PLAN, MOCK_USAGE))
def test_plan_tasks_cache_miss(mock_chat, mock_embed, mock_get, mock_sem, mock_set):
    """First call — should call LLM and cache result."""
    from src.agents.task_planning import plan_tasks_with_semantic
    result = plan_tasks_with_semantic(VALID_GOAL)
    assert result["cache_hit"] == "none"
    assert result["tokens_used"] == 800
    assert len(result["tasks"]["tasks"]) == 3
    mock_chat.assert_called_once()
    mock_set.assert_called_once()


@patch("src.agents.task_planning.set_cached")
@patch("src.agents.task_planning.semantic_lookup", return_value=(None, 0.0))
@patch("src.agents.task_planning.get_embedding", return_value=[0.2] * 768)
@patch("src.agents.task_planning.call_llm", return_value=(VALID_PLAN, MOCK_USAGE))
def test_plan_tasks_exact_cache_hit(mock_chat, mock_embed, mock_sem, mock_set):
    """Exact cache hit — returns immediately, 0 tokens."""
    from src.agents.task_planning import plan_tasks_with_semantic
    cached_entry = {"tasks_json": VALID_PLAN}
    with patch("src.agents.task_planning.get_cached", return_value=cached_entry):
        result = plan_tasks_with_semantic(VALID_GOAL)
    assert result["cache_hit"] == "exact"
    assert result["tokens_used"] == 0
    mock_chat.assert_not_called()


# ── Validation & retry ────────────────────────────────────────────────────────

@patch("src.agents.task_planning.set_cached")
@patch("src.agents.task_planning.semantic_lookup", return_value=(None, 0.0))
@patch("src.agents.task_planning.get_cached", return_value=None)
@patch("src.agents.task_planning.get_embedding", return_value=[0.2] * 768)
@patch("src.agents.task_planning.call_llm")
def test_plan_tasks_retry_on_validation_failure(mock_chat, mock_embed, mock_get, mock_sem, mock_set):
    """
    First LLM call returns a plan with a bad dependency.
    Second call (corrective prompt) returns a valid plan.
    """
    from src.agents.task_planning import plan_tasks_with_semantic

    bad_plan = {
        **VALID_PLAN,
        "tasks": [
            {**VALID_PLAN["tasks"][0], "depends_on": ["t_nonexistent"]},
            *VALID_PLAN["tasks"][1:],
        ],
    }
    mock_chat.side_effect = [
        (bad_plan, MOCK_USAGE),    # first attempt -> invalid
        (VALID_PLAN, MOCK_USAGE),  # retry -> valid
    ]

    result = plan_tasks_with_semantic(VALID_GOAL, retry=True)
    assert result["cache_hit"] == "none"
    assert mock_chat.call_count == 2  # first + corrective retry


@patch("src.agents.task_planning.set_cached")
@patch("src.agents.task_planning.semantic_lookup", return_value=(None, 0.0))
@patch("src.agents.task_planning.get_cached", return_value=None)
@patch("src.agents.task_planning.get_embedding", return_value=[0.2] * 768)
@patch("src.agents.task_planning.call_llm")
def test_plan_tasks_raises_if_retry_also_fails(mock_chat, mock_embed, mock_get, mock_sem, mock_set):
    """Both attempts return invalid plans — should raise ValueError."""
    from src.agents.task_planning import plan_tasks_with_semantic

    cyclic_plan = {
        **VALID_PLAN,
        "tasks": [
            {"id": "t1", "title": "A", "description": ".", "depends_on": ["t2"], "estimated_effort": "S"},
            {"id": "t2", "title": "B", "description": ".", "depends_on": ["t1"], "estimated_effort": "S"},
        ],
        "execution_order": ["t1", "t2"],
        "parallel_groups": [],
    }
    mock_chat.return_value = (cyclic_plan, MOCK_USAGE)

    with pytest.raises(ValueError, match="Cycle detected"):
        plan_tasks_with_semantic(VALID_GOAL, retry=True)
