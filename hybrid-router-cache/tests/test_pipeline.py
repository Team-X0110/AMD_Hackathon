"""
tests/test_pipeline.py — Integration tests for run_pipeline.

Mocks both agents so the pipeline logic (ordering, aggregation, logging) is tested
independently of real LLM calls.

Run:
    python -m pytest tests/test_pipeline.py -v
"""
from __future__ import annotations
from unittest.mock import patch, MagicMock
import sys

# ── Pre-stub heavy deps so pipeline.py can be imported without FAISS/transformers ──
# These are replaced by real patches inside each test anyway.
_stub_cache = MagicMock()
_stub_cache.semantic_lookup = MagicMock(return_value=(None, 0.0))
_stub_cache.add_to_local_cache = MagicMock()
sys.modules.setdefault("src.cache.global_semantic_cache", _stub_cache)

import src.pipeline  # noqa: E402 — must be imported after stub so @patch can resolve it

MOCK_GOAL_RESULT_NONE = {
    "goal": {
        "intent": "build an API",
        "entities": ["API"],
        "constraints": [],
        "success_criteria": ["API works"],
        "domain": "software engineering",
        "complexity_hint": "low",
    },
    "cache_hit": "none",
    "tokens_used": 400,
    "fireworks_tokens": 0,
    "routing": [{"tier": "local", "success": True}],
}

MOCK_PLAN_RESULT_NONE = {
    "tasks": {
        "tasks": [{"id": "t1", "title": "Do it", "description": ".", "depends_on": [], "estimated_effort": "S"}],
        "execution_order": ["t1"],
        "parallel_groups": [["t1"]],
    },
    "cache_hit": "none",
    "tokens_used": 800,
    "fireworks_tokens": 0,
    "routing": [{"tier": "local", "success": True}],
}

MOCK_GOAL_RESULT_EXACT = {**MOCK_GOAL_RESULT_NONE, "cache_hit": "exact", "tokens_used": 0}
MOCK_PLAN_RESULT_EXACT = {**MOCK_PLAN_RESULT_NONE, "cache_hit": "exact", "tokens_used": 0}


@patch("src.pipeline._log_run")  # suppress Firestore/disk writes in unit tests
@patch("src.pipeline.add_to_local_cache")
@patch("src.pipeline.global_semantic_lookup", return_value=(None, 0.0))
@patch("src.pipeline.plan_tasks_with_semantic", return_value=MOCK_PLAN_RESULT_NONE)
@patch("src.pipeline.understand_goal_with_semantic", return_value=MOCK_GOAL_RESULT_NONE)
def test_pipeline_cache_miss(mock_goal, mock_plan, mock_sem, mock_cache, mock_log):
    """Cold start — both agents miss, tokens > 0."""
    from src.pipeline import run_pipeline
    result = run_pipeline("build a todo API")
    assert result["tokens_used"] == 1200
    assert result["fireworks_tokens"] == 0
    assert "routing" in result
    assert result["cache_hits"]["goal"] == "none"
    assert result["cache_hits"]["plan"] == "none"
    assert "latency_sec" in result
    assert "goal" in result
    assert "tasks" in result


@patch("src.pipeline._log_run")
@patch("src.pipeline.add_to_local_cache")
@patch("src.pipeline.global_semantic_lookup", return_value=(None, 0.0))
@patch("src.pipeline.plan_tasks_with_semantic", return_value=MOCK_PLAN_RESULT_EXACT)
@patch("src.pipeline.understand_goal_with_semantic", return_value=MOCK_GOAL_RESULT_EXACT)
def test_pipeline_full_cache_hit(mock_goal, mock_plan, mock_sem, mock_cache, mock_log):
    """Both agents hit exact cache — zero tokens."""
    from src.pipeline import run_pipeline
    result = run_pipeline("build a todo API")
    assert result["tokens_used"] == 0
    assert result["cache_hits"]["goal"] == "exact"
    assert result["cache_hits"]["plan"] == "exact"


@patch("src.pipeline._log_run")
@patch("src.pipeline.add_to_local_cache")
@patch("src.pipeline.global_semantic_lookup", return_value=(None, 0.0))
@patch("src.pipeline.plan_tasks_with_semantic", return_value=MOCK_PLAN_RESULT_EXACT)
@patch("src.pipeline.understand_goal_with_semantic",
       return_value={**MOCK_GOAL_RESULT_NONE, "cache_hit": "semantic(0.94)", "tokens_used": 0})
def test_pipeline_semantic_goal_hit(mock_goal, mock_plan, mock_sem, mock_cache, mock_log):
    """Goal hits semantic cache, plan hits exact cache — zero tokens total."""
    from src.pipeline import run_pipeline
    result = run_pipeline("create a todo REST API")
    assert result["tokens_used"] == 0
    assert "semantic" in result["cache_hits"]["goal"]


@patch("src.pipeline._log_run")
@patch("src.pipeline.add_to_local_cache")
@patch("src.pipeline.global_semantic_lookup", return_value=(None, 0.0))
@patch("src.pipeline.plan_tasks_with_semantic", return_value=MOCK_PLAN_RESULT_NONE)
@patch("src.pipeline.understand_goal_with_semantic", return_value=MOCK_GOAL_RESULT_NONE)
def test_pipeline_returns_latency(mock_goal, mock_plan, mock_sem, mock_cache, mock_log):
    """Latency field must be a non-negative float."""
    from src.pipeline import run_pipeline
    result = run_pipeline("any prompt")
    assert isinstance(result["latency_sec"], float)
    assert result["latency_sec"] >= 0
