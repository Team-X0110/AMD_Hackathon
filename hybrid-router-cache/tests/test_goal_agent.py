"""
tests/test_goal_agent.py — Unit tests for the Goal Understanding Agent.

Strategy:
  - Mock call_llm, get_embedding, and semantic_lookup so tests never hit real APIs.
  - The cache layer (exact/semantic) functions are mocked at the agent module boundary.

Run:
    python -m pytest tests/test_goal_agent.py -v
"""
from __future__ import annotations
import pytest
from unittest.mock import patch, MagicMock

TEST_GOAL_COLLECTION = "goal_cache_test_ci"

# A valid goal JSON response from the LLM
VALID_GOAL = {
    "intent": "build a REST API with authentication",
    "entities": ["REST API", "authentication", "user management"],
    "constraints": ["must use JWT", "PostgreSQL backend"],
    "success_criteria": ["API returns 200 for valid requests", "invalid tokens get 401"],
    "domain": "software engineering",
    "complexity_hint": "medium",
}

MOCK_USAGE = {"total_tokens": 350, "prompt_tokens": 200, "completion_tokens": 150}


# ── Happy path ────────────────────────────────────────────────────────────────

@patch("src.agents.goal_understanding.set_cached")
@patch("src.agents.goal_understanding.semantic_lookup", return_value=(None, 0.0))
@patch("src.agents.goal_understanding.get_cached", return_value=None)
@patch("src.agents.goal_understanding.get_embedding", return_value=[0.1] * 768)
@patch("src.agents.goal_understanding.call_llm", return_value=(VALID_GOAL, MOCK_USAGE))
def test_understand_goal_cache_miss(mock_chat, mock_embed, mock_get, mock_sem, mock_set):
    """First call — no cache, should call LLM and store result."""
    from src.agents.goal_understanding import understand_goal_with_semantic
    result = understand_goal_with_semantic("build me a REST API")
    assert result["cache_hit"] == "none"
    assert result["tokens_used"] == 350
    assert result["goal"]["complexity_hint"] == "medium"
    mock_chat.assert_called_once()
    mock_set.assert_called_once()


@patch("src.agents.goal_understanding.set_cached")
@patch("src.agents.goal_understanding.semantic_lookup", return_value=(None, 0.0))
@patch("src.agents.goal_understanding.get_embedding", return_value=[0.1] * 768)
@patch("src.agents.goal_understanding.call_llm", return_value=(VALID_GOAL, MOCK_USAGE))
def test_understand_goal_exact_cache_hit(mock_chat, mock_embed, mock_sem, mock_set):
    """Exact cache hit — returns immediately, no LLM call."""
    from src.agents.goal_understanding import understand_goal_with_semantic
    cached_entry = {"goal_json": VALID_GOAL}
    with patch("src.agents.goal_understanding.get_cached", return_value=cached_entry):
        result = understand_goal_with_semantic("build me a REST API")
    assert result["cache_hit"] == "exact"
    assert result["tokens_used"] == 0
    mock_chat.assert_not_called()


# ── Schema validation ─────────────────────────────────────────────────────────

@patch("src.agents.goal_understanding.set_cached")
@patch("src.agents.goal_understanding.semantic_lookup", return_value=(None, 0.0))
@patch("src.agents.goal_understanding.get_cached", return_value=None)
@patch("src.agents.goal_understanding.get_embedding", return_value=[0.1] * 768)
@patch("src.agents.goal_understanding.call_llm")
def test_understand_goal_invalid_schema_raises(mock_chat, mock_embed, mock_get, mock_sem, mock_set):
    """LLM returning bad JSON should raise ValueError (not swallow it)."""
    from src.agents.goal_understanding import understand_goal_with_semantic
    bad_goal = {"intent": "missing required keys"}  # no complexity_hint etc.
    mock_chat.return_value = (bad_goal, MOCK_USAGE)
    with pytest.raises(ValueError, match="missing required keys"):
        understand_goal_with_semantic("schema_validation_test")


@patch("src.agents.goal_understanding.set_cached")
@patch("src.agents.goal_understanding.semantic_lookup", return_value=(None, 0.0))
@patch("src.agents.goal_understanding.get_cached", return_value=None)
@patch("src.agents.goal_understanding.get_embedding", return_value=[0.1] * 768)
@patch("src.agents.goal_understanding.call_llm")
def test_understand_goal_bad_complexity_hint_raises(mock_chat, mock_embed, mock_get, mock_sem, mock_set):
    """'complexity_hint' must be low|medium|high."""
    from src.agents.goal_understanding import understand_goal_with_semantic
    bad_goal = {**VALID_GOAL, "complexity_hint": "extreme"}
    mock_chat.return_value = (bad_goal, MOCK_USAGE)
    with pytest.raises(ValueError, match="Invalid complexity_hint"):
        understand_goal_with_semantic("bad_complexity_test")
