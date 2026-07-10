"""
tests/test_routing_engine.py
=============================
Unit tests for Module 3.5 — Routing Engine.

Tests cover:
- ModelRegistry loading and normalisation
- UtilityScorer component scores
- EscalationPolicy tier skip logic
- RoutingEngine local-first preference
- RoutingEngine progressive escalation
- RoutingEngine score ranking
"""

from __future__ import annotations

import json
import os
import tempfile
import pytest
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

# Project root on sys.path is assumed (run `pytest` from AMD_Hackathon/)
from core.types import (
    ComplexityEstimationResult,
    ComplexityLevel,
    ConfidenceEngineResult,
    ExecutionTier,
    FeatureExtractionResult,
    ModelProfile,
    RiskLevel,
    RoutingContext,
    TaskType,
)
from routing.escalation_policy import EscalationPolicy
from routing.model_registry import ModelRegistry
from routing.utility_scorer import UtilityScorer
from telemetry.telemetry_store import TelemetryStore


# ---------------------------------------------------------------------------
# FIXTURES
# ---------------------------------------------------------------------------

MODELS_JSON_PATH = str(
    Path(__file__).parent.parent / "model_data" / "models.json"
)
ROUTING_CONFIG_PATH = str(
    Path(__file__).parent.parent / "config" / "routing_config.yaml"
)
VERIFIER_CONFIG_PATH = str(
    Path(__file__).parent.parent / "config" / "verifier_config.yaml"
)


def _make_context(
    task_type: TaskType = TaskType.GENERAL_CHAT,
    complexity: ComplexityLevel = ComplexityLevel.SIMPLE,
    risk: RiskLevel = RiskLevel.LOW,
    confidence: float = 0.75,
    local_confidence: float = 0.70,
    requires_vision: bool = False,
    requires_coding: bool = False,
    requires_reasoning: bool = False,
    force_escalate: ExecutionTier = None,
) -> RoutingContext:
    features = FeatureExtractionResult(
        request_id="test-001",
        prompt="Explain what AI is.",
        prompt_tokens_estimated=10,
        detected_task_types=[task_type],
        primary_task_type=task_type,
        has_code_block=requires_coding,
        has_image=requires_vision,
        has_structured_output_requirement=False,
        requires_citations=False,
        expected_output_format="text",
        detected_language="en",
        domain_keywords=["ai", "explain"],
        tool_schemas_provided=False,
    )
    complexity_result = ComplexityEstimationResult(
        request_id="test-001",
        complexity_level=complexity,
        complexity_score=0.2,
        risk_level=risk,
        risk_score=0.1,
        requires_reasoning=requires_reasoning,
        requires_vision=requires_vision,
        requires_coding=requires_coding,
        requires_long_context=False,
        estimated_output_tokens=100,
        domain="general",
    )
    confidence_result = ConfidenceEngineResult(
        request_id="test-001",
        overall_confidence=confidence,
        local_can_handle=local_confidence >= 0.60,
        local_confidence=local_confidence,
        recommended_min_tier=ExecutionTier.LOCAL,
        force_escalate_to=force_escalate,
        confidence_reasoning="Test context",
    )
    return RoutingContext(
        request_id="test-001",
        features=features,
        complexity=complexity_result,
        confidence=confidence_result,
        original_messages=[{"role": "user", "content": "Explain what AI is."}],
    )


@pytest.fixture
def registry() -> ModelRegistry:
    reg = ModelRegistry(MODELS_JSON_PATH, ROUTING_CONFIG_PATH)
    reg.load()
    return reg


@pytest.fixture
def scorer() -> UtilityScorer:
    return UtilityScorer(ROUTING_CONFIG_PATH)


@pytest.fixture
def policy() -> EscalationPolicy:
    return EscalationPolicy(ROUTING_CONFIG_PATH)


@pytest.fixture
def telemetry_store(tmp_path) -> TelemetryStore:
    return TelemetryStore(str(tmp_path / "telemetry.jsonl"))


# ---------------------------------------------------------------------------
# MODEL REGISTRY TESTS
# ---------------------------------------------------------------------------

class TestModelRegistry:
    def test_loads_all_models(self, registry):
        profiles = registry.get_all_profiles()
        assert len(profiles) >= 1, "Should load at least one model"

    def test_all_scores_normalised(self, registry):
        for profile in registry.get_all_profiles():
            assert 0.0 <= profile.quality_score <= 1.0, f"{profile.model_id} quality_score out of range"
            assert 0.0 <= profile.reasoning_score <= 1.0
            assert 0.0 <= profile.coding_score <= 1.0
            assert 0.0 <= profile.cost_score <= 1.0
            assert 0.0 <= profile.latency_score <= 1.0

    def test_get_profile_by_id(self, registry):
        profiles = registry.get_all_profiles()
        if profiles:
            model = profiles[0]
            fetched = registry.get_profile(model.model_id)
            assert fetched is not None
            assert fetched.model_id == model.model_id

    def test_get_profile_unknown_returns_none(self, registry):
        result = registry.get_profile("accounts/fireworks/models/does-not-exist")
        assert result is None

    def test_get_models_in_tier(self, registry):
        # "Cheap" tier should exist in models.json
        cheap_models = registry.get_models_in_tier("Cheap")
        # May be 0 if no Cheap tier models — just ensure it returns a list
        assert isinstance(cheap_models, list)

    def test_get_best_coding_model(self, registry):
        best = registry.get_best_coding_model(0.0)
        assert best is not None
        assert best.coding_score >= 0.0

    def test_tier_order_assigned(self, registry):
        for profile in registry.get_all_profiles():
            assert profile.tier_order >= 0, f"{profile.model_id} has invalid tier_order"


# ---------------------------------------------------------------------------
# UTILITY SCORER TESTS
# ---------------------------------------------------------------------------

class TestUtilityScorer:
    def test_score_returns_candidate(self, scorer, registry):
        profiles = registry.get_all_profiles()
        if not profiles:
            pytest.skip("No models loaded")
        context = _make_context()
        candidate = scorer.score(profiles[0], context, history_score=0.75)
        assert 0.0 <= candidate.utility_score <= 1.0

    def test_vision_required_disqualifies_non_vision(self, scorer, registry):
        context = _make_context(requires_vision=True)
        for profile in registry.get_all_profiles():
            if not profile.has_vision:
                candidate = scorer.score(profile, context, 0.75)
                assert not candidate.meets_capability_requirements
                assert len(candidate.disqualification_reasons) > 0

    def test_score_all_returns_sorted(self, scorer, registry):
        profiles = registry.get_all_profiles()
        if len(profiles) < 2:
            pytest.skip("Need at least 2 models")
        context = _make_context()
        history = {p.model_id: 0.75 for p in profiles}
        scored = scorer.score_all(profiles, context, history)
        # First should have highest or equal utility_score
        scores = [c.utility_score for c in scored if c.meets_capability_requirements]
        assert scores == sorted(scores, reverse=True)

    def test_cost_penalty_favours_cheaper(self, scorer, registry):
        """Cheaper models should have higher cost_penalty component."""
        profiles = registry.get_all_profiles()
        if len(profiles) < 2:
            pytest.skip("Need at least 2 models")
        context = _make_context()
        scored = {
            p.model_id: scorer.score(p, context, 0.75)
            for p in profiles
        }
        # Find the model with lowest output cost and highest output cost
        by_cost = sorted(profiles, key=lambda p: p.output_cost_per_million)
        cheapest_id = by_cost[0].model_id
        priciest_id = by_cost[-1].model_id
        if cheapest_id != priciest_id:
            cheap_penalty = scored[cheapest_id].score_breakdown.get("cost_penalty", 0)
            pricey_penalty = scored[priciest_id].score_breakdown.get("cost_penalty", 0)
            assert cheap_penalty >= pricey_penalty


# ---------------------------------------------------------------------------
# ESCALATION POLICY TESTS
# ---------------------------------------------------------------------------

class TestEscalationPolicy:
    def test_local_skipped_if_vision(self, policy):
        context = _make_context(requires_vision=True)
        assert policy.should_skip_tier(0, context), "LOCAL should be skipped for vision"

    def test_local_not_skipped_for_text(self, policy):
        context = _make_context(requires_vision=False, local_confidence=0.80, confidence=0.80)
        # Should not skip local for a normal text task with sufficient confidence
        assert not policy.should_skip_tier(0, context)

    def test_cheap_skipped_for_expert(self, policy):
        context = _make_context(
            complexity=ComplexityLevel.EXPERT, confidence=0.85
        )
        assert policy.should_skip_tier(1, context), "CHEAP should be skipped for EXPERT tasks"

    def test_cheap_skipped_for_critical_risk(self, policy):
        context = _make_context(risk=RiskLevel.CRITICAL, confidence=0.85)
        assert policy.should_skip_tier(1, context), "CHEAP should be skipped for CRITICAL risk"

    def test_force_escalate_overrides_starting_tier(self, policy):
        context = _make_context(force_escalate=ExecutionTier.PREMIUM)
        starting = policy.get_starting_tier_order(context)
        # PREMIUM order = 3
        assert starting == 3

    def test_get_next_tier_ascending(self, policy):
        context = _make_context(confidence=0.85)
        # Starting from tier 1 (CHEAP), next should be >= 2
        next_tier = policy.get_next_tier_order(1, context)
        assert next_tier is None or next_tier > 1

    def test_tier_label_round_trip(self, policy):
        label = "PREMIUM"
        order = policy.tier_label_to_order(label)
        recovered = policy.tier_order_to_label(order)
        assert recovered == label

    def test_no_more_tiers_above_ultra_premium(self, policy):
        context = _make_context()
        # Tier 4 is the last
        next_tier = policy.get_next_tier_order(4, context)
        assert next_tier is None
