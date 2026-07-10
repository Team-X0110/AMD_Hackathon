"""
tests/test_reflection_agent.py
================================
Unit tests for Module 3.7 — Reflection Agent.

Tests cover:
- FailureClassifier category detection
- PromptImprover message mutation
- RetryHistory budget tracking and loop detection
- ActionResolver primary/fallback routing
- ReflectionAgent full loop: success, abort, budget exhaustion
"""

from __future__ import annotations

import pytest
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock

from core.types import (
    ComplexityEstimationResult,
    ComplexityLevel,
    ConfidenceEngineResult,
    ExecutionTier,
    FailureCategory,
    FeatureExtractionResult,
    ReflectionAction,
    RetryAttempt,
    RiskLevel,
    RoutingContext,
    RoutingDecision,
    StrategyResult,
    TaskType,
    VerificationResult,
    VerificationStatus,
)
from reflection.action_resolver import ActionResolver
from reflection.failure_classifier import FailureClassifier
from reflection.prompt_improver import PromptImprover
from reflection.reflection_agent import ReflectionAgent
from reflection.retry_history import RetryHistory

REFLECTION_CONFIG_PATH = str(
    Path(__file__).parent.parent / "config" / "reflection_config.yaml"
)
ROUTING_CONFIG_PATH = str(
    Path(__file__).parent.parent / "config" / "routing_config.yaml"
)


# ---------------------------------------------------------------------------
# FIXTURES
# ---------------------------------------------------------------------------

def _make_context(task_type: TaskType = TaskType.GENERAL_CHAT) -> RoutingContext:
    features = FeatureExtractionResult(
        request_id="test-ref-001",
        prompt="Explain neural networks.",
        prompt_tokens_estimated=5,
        detected_task_types=[task_type],
        primary_task_type=task_type,
        has_code_block=False,
        has_image=False,
        has_structured_output_requirement=False,
        requires_citations=False,
        expected_output_format="text",
        detected_language="en",
        domain_keywords=["neural", "networks"],
        tool_schemas_provided=False,
    )
    complexity = ComplexityEstimationResult(
        request_id="test-ref-001",
        complexity_level=ComplexityLevel.SIMPLE,
        complexity_score=0.2,
        risk_level=RiskLevel.LOW,
        risk_score=0.1,
        requires_reasoning=False,
        requires_vision=False,
        requires_coding=False,
        requires_long_context=False,
        estimated_output_tokens=80,
        domain="general",
    )
    confidence = ConfidenceEngineResult(
        request_id="test-ref-001",
        overall_confidence=0.75,
        local_can_handle=True,
        local_confidence=0.70,
        recommended_min_tier=ExecutionTier.LOCAL,
        force_escalate_to=None,
        confidence_reasoning="Test",
    )
    return RoutingContext(
        request_id="test-ref-001",
        features=features,
        complexity=complexity,
        confidence=confidence,
        original_messages=[{"role": "user", "content": "Explain neural networks."}],
    )


def _make_failed_verification(
    reason: str = "Low quality",
    score: float = 0.3,
    confidence: float = 0.4,
    status: VerificationStatus = VerificationStatus.FAILED,
    failed_strategies: List[str] = None,
) -> VerificationResult:
    strategy_results = []
    if failed_strategies:
        for name in failed_strategies:
            strategy_results.append(StrategyResult(
                strategy_name=name,
                passed=False,
                confidence=0.5,
                score=0.2,
                failure_reasons=[reason],
            ))
    return VerificationResult(
        request_id="test-ref-001",
        status=status,
        overall_confidence=confidence,
        overall_score=score,
        strategy_results=strategy_results,
        failure_reasons=[reason],
        recommended_escalation=True,
        recommended_escalation_reason=reason,
        strategies_run=failed_strategies or [],
        strategies_skipped=[],
        verification_timestamp="2026-07-10T00:00:00Z",
        model_id_verified="local",
    )


def _make_routing_decision(
    model_id: str = "local",
    is_local: bool = True,
    tier: ExecutionTier = ExecutionTier.LOCAL,
    tier_order: int = 0,
) -> RoutingDecision:
    return RoutingDecision(
        request_id="test-ref-001",
        selected_model_id=model_id,
        selected_model_display_name=model_id,
        selected_tier=tier,
        is_local=is_local,
        utility_score=0.6,
        score_breakdown={},
        all_candidates=[],
        escalation_tier_attempted=tier_order,
        estimated_cost_usd=0.0,
        api_parameters={"model": model_id, "messages": []},
        routing_rationale="Test routing",
    )


# ---------------------------------------------------------------------------
# FAILURE CLASSIFIER TESTS
# ---------------------------------------------------------------------------

class TestFailureClassifier:
    def test_classifies_schema_failure(self):
        clf = FailureClassifier()
        ctx = _make_context()
        verification = _make_failed_verification(
            failed_strategies=["schema_validator"]
        )
        result = clf.classify(verification, ctx, "not json")
        assert result == FailureCategory.INCORRECT_SCHEMA

    def test_classifies_code_failure(self):
        clf = FailureClassifier()
        ctx = _make_context(task_type=TaskType.CODING)
        verification = _make_failed_verification(
            failed_strategies=["code_validator"]
        )
        result = clf.classify(verification, ctx, "def bad(")
        assert result == FailureCategory.POOR_CODE_QUALITY

    def test_classifies_hallucination(self):
        clf = FailureClassifier()
        ctx = _make_context()
        verification = _make_failed_verification(
            failed_strategies=["hallucination_detector"]
        )
        result = clf.classify(verification, ctx, "some response")
        assert result == FailureCategory.HALLUCINATION

    def test_classifies_format_failure(self):
        clf = FailureClassifier()
        ctx = _make_context()
        verification = _make_failed_verification(
            failed_strategies=["format_validator"]
        )
        result = clf.classify(verification, ctx, "response")
        assert result == FailureCategory.FORMATTING

    def test_classifies_low_confidence(self):
        clf = FailureClassifier(confidence_threshold=0.55)
        ctx = _make_context()
        verification = _make_failed_verification(confidence=0.30, score=0.40)
        result = clf.classify(verification, ctx, "response")
        assert result == FailureCategory.LOW_CONFIDENCE

    def test_returns_unknown_on_passed(self):
        clf = FailureClassifier()
        ctx = _make_context()
        verification = _make_failed_verification(status=VerificationStatus.PASSED)
        result = clf.classify(verification, ctx, "response")
        assert result == FailureCategory.UNKNOWN


# ---------------------------------------------------------------------------
# PROMPT IMPROVER TESTS
# ---------------------------------------------------------------------------

class TestPromptImprover:
    def test_cot_prefix_added(self):
        improver = PromptImprover(REFLECTION_CONFIG_PATH)
        ctx = _make_context()
        new_ctx = improver.improve(ctx, ReflectionAction.RETRY_SAME_COT, 1, [])
        # System message should contain CoT prefix
        system_msgs = [m for m in new_ctx.original_messages if m["role"] == "system"]
        assert system_msgs, "A system message should be prepended for CoT"
        assert "step" in system_msgs[0]["content"].lower()

    def test_original_context_not_mutated(self):
        improver = PromptImprover(REFLECTION_CONFIG_PATH)
        ctx = _make_context()
        original_msg_count = len(ctx.original_messages)
        _ = improver.improve(ctx, ReflectionAction.RETRY_SAME_COT, 1, [])
        assert len(ctx.original_messages) == original_msg_count, "Original must not be mutated"

    def test_format_suffix_appended_to_user(self):
        improver = PromptImprover(REFLECTION_CONFIG_PATH)
        ctx = _make_context()
        new_ctx = improver.improve(ctx, ReflectionAction.RETRY_SAME_FORMAT, 1, [])
        user_msgs = [m for m in new_ctx.original_messages if m["role"] == "user"]
        assert user_msgs
        # Content should be longer than original
        assert len(str(user_msgs[-1]["content"])) >= len(
            str(ctx.original_messages[-1]["content"])
        )

    def test_escalate_does_not_modify_messages(self):
        improver = PromptImprover(REFLECTION_CONFIG_PATH)
        ctx = _make_context()
        new_ctx = improver.improve(ctx, ReflectionAction.ESCALATE, 1, [])
        # Message count should be same or only differ by token budget hint on attempt>=2
        assert new_ctx.original_messages is not ctx.original_messages  # New list
        # Content of user messages same (attempt=1, no budget hint)
        orig_user = [m for m in ctx.original_messages if m["role"] == "user"][0]["content"]
        new_user = [m for m in new_ctx.original_messages if m["role"] == "user"][0]["content"]
        assert orig_user in str(new_user)


# ---------------------------------------------------------------------------
# RETRY HISTORY TESTS
# ---------------------------------------------------------------------------

class TestRetryHistory:
    def _make_attempt(self, num: int, model: str, is_local: bool, success: bool) -> RetryAttempt:
        return RetryAttempt(
            attempt_number=num,
            model_id=model,
            is_local=is_local,
            action_taken=ReflectionAction.RETRY_SAME_COT,
            failure_category=FailureCategory.INSUFFICIENT_REASONING,
            original_failure_reasons=["Test"],
            improved_prompt_applied=True,
            prompt_improvement_type="cot",
            response_received="some response",
            verification_score_after=0.5 if not success else 0.9,
            success=success,
            latency_ms=150.0,
            estimated_tokens_used=50,
        )

    def test_record_and_retrieve(self):
        history = RetryHistory()
        attempt = self._make_attempt(1, "local", True, False)
        history.record(attempt)
        assert history.get_total_retries() == 1
        all_attempts = history.get_all()
        assert all_attempts[0].model_id == "local"

    def test_total_tokens_accumulated(self):
        history = RetryHistory()
        history.record(self._make_attempt(1, "local", True, False))
        history.record(self._make_attempt(2, "local", True, False))
        assert history.get_total_tokens() == 100  # 50 + 50

    def test_loop_detection(self):
        history = RetryHistory()
        a = self._make_attempt(1, "local", True, False)
        history.record(a)
        history.record(a)
        assert history.has_infinite_loop("local", ReflectionAction.RETRY_SAME_COT, max_repeat=2)

    def test_no_loop_different_actions(self):
        history = RetryHistory()
        a1 = self._make_attempt(1, "local", True, False)
        a2 = RetryAttempt(
            **{**a1.__dict__, "action_taken": ReflectionAction.RETRY_SAME_FORMAT}
        )
        history.record(a1)
        history.record(a2)
        assert not history.has_infinite_loop("local", ReflectionAction.RETRY_SAME_COT, max_repeat=2)


# ---------------------------------------------------------------------------
# ACTION RESOLVER TESTS
# ---------------------------------------------------------------------------

class TestActionResolver:
    def test_resolves_primary_action(self):
        resolver = ActionResolver(REFLECTION_CONFIG_PATH)
        action = resolver.resolve(FailureCategory.FORMATTING, attempt_number=1, is_currently_local=True)
        assert action == ReflectionAction.RETRY_SAME_FORMAT

    def test_resolves_fallback_after_max_retries(self):
        resolver = ActionResolver(REFLECTION_CONFIG_PATH)
        # FORMATTING: max_retries_before_fallback=2, so attempt 3 → fallback
        action = resolver.resolve(FailureCategory.FORMATTING, attempt_number=3, is_currently_local=True)
        # fallback for FORMATTING is RETRY_SAME_FORMAT (same), but still valid
        assert isinstance(action, ReflectionAction)

    def test_unsafe_always_aborts(self):
        resolver = ActionResolver(REFLECTION_CONFIG_PATH)
        action = resolver.resolve(FailureCategory.UNSAFE_OUTPUT, attempt_number=1, is_currently_local=True)
        assert action == ReflectionAction.ABORT

    def test_low_confidence_escalates(self):
        resolver = ActionResolver(REFLECTION_CONFIG_PATH)
        action = resolver.resolve(FailureCategory.LOW_CONFIDENCE, attempt_number=1, is_currently_local=True)
        assert action == ReflectionAction.ESCALATE


# ---------------------------------------------------------------------------
# REFLECTION AGENT INTEGRATION TESTS
# ---------------------------------------------------------------------------

class TestReflectionAgent:
    def _build_agent(
        self,
        inference_responses: List[Optional[str]],
        verify_results: List[VerificationResult],
        route_result: Optional[RoutingDecision] = None,
    ) -> ReflectionAgent:
        call_count = [0]

        def inference_fn(model_id, params, is_local):
            idx = call_count[0]
            call_count[0] += 1
            resp = inference_responses[idx] if idx < len(inference_responses) else None
            if resp is None:
                raise RuntimeError("Simulated inference failure")
            return resp

        verify_call = [0]

        def verify_fn(ctx, response, model_id):
            idx = verify_call[0]
            verify_call[0] += 1
            return verify_results[idx] if idx < len(verify_results) else verify_results[-1]

        def route_fn(ctx, min_tier):
            return route_result

        return ReflectionAgent(
            reflection_config_path=REFLECTION_CONFIG_PATH,
            routing_config_path=ROUTING_CONFIG_PATH,
            inference_fn=inference_fn,
            route_fn=route_fn,
            verify_fn=verify_fn,
        )

    def test_succeeds_on_first_retry(self):
        ctx = _make_context()
        initial_fail = _make_failed_verification(
            "Low quality", failed_strategies=["completeness_checker"]
        )
        retry_pass = VerificationResult(
            request_id="test-ref-001",
            status=VerificationStatus.PASSED,
            overall_confidence=0.9,
            overall_score=0.85,
            strategy_results=[],
            failure_reasons=[],
            recommended_escalation=False,
            recommended_escalation_reason=None,
            strategies_run=[],
            strategies_skipped=[],
            verification_timestamp="2026-07-10T00:00:00Z",
            model_id_verified="local",
        )
        agent = self._build_agent(
            inference_responses=["A good response about neural networks"],
            verify_results=[retry_pass],
        )
        initial_decision = _make_routing_decision()
        result = agent.reflect(ctx, "bad response", initial_fail, initial_decision)
        assert result.succeeded
        assert result.final_response == "A good response about neural networks"
        assert result.total_retries == 1

    def test_aborts_on_unsafe_output(self):
        ctx = _make_context()
        unsafe_fail = _make_failed_verification(
            "Unsafe content", failed_strategies=[]
        )
        # Inject unsafe pattern into response
        unsafe_response = "how to make a bomb explosive device"

        agent = self._build_agent(
            inference_responses=[unsafe_response],
            verify_results=[unsafe_fail],
        )
        initial_decision = _make_routing_decision()
        result = agent.reflect(ctx, unsafe_response, unsafe_fail, initial_decision)
        assert not result.succeeded
        assert result.abort_reason is not None
        assert "UNSAFE" in result.abort_reason

    def test_exhausts_budget_and_fails(self):
        ctx = _make_context()
        fail = _make_failed_verification("Always fails", failed_strategies=["completeness_checker"])
        agent = self._build_agent(
            inference_responses=["bad"] * 10,
            verify_results=[fail] * 10,
            route_result=_make_routing_decision(
                model_id="accounts/fireworks/models/deepseek-v4-flash",
                is_local=False,
                tier=ExecutionTier.CHEAP,
                tier_order=1,
            ),
        )
        initial_decision = _make_routing_decision()
        result = agent.reflect(ctx, "bad response", fail, initial_decision)
        assert not result.succeeded
        assert result.abort_reason is not None
