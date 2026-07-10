"""
tests/test_verifier.py
=======================
Unit tests for Module 3.6 — Local Verifier.

Tests cover:
- Individual strategy should_run() gating
- Individual strategy _run_check() correctness
- Verifier orchestrator aggregation
- Hard minimum enforcement
- Escalation recommendation logic
"""

from __future__ import annotations

import pytest
from pathlib import Path
from typing import Any, Dict

from core.types import (
    ComplexityEstimationResult,
    ComplexityLevel,
    ConfidenceEngineResult,
    ExecutionTier,
    FeatureExtractionResult,
    RiskLevel,
    RoutingContext,
    TaskType,
)
from verification.strategies.citation_validator import CitationValidatorStrategy
from verification.strategies.code_validator import CodeValidatorStrategy
from verification.strategies.completeness_checker import CompletenessCheckerStrategy
from verification.strategies.format_validator import FormatValidatorStrategy
from verification.strategies.hallucination_detector import HallucinationDetectorStrategy
from verification.strategies.schema_validator import SchemaValidatorStrategy
from verification.verifier import Verifier

VERIFIER_CONFIG_PATH = str(
    Path(__file__).parent.parent / "config" / "verifier_config.yaml"
)


# ---------------------------------------------------------------------------
# FIXTURES
# ---------------------------------------------------------------------------

def _make_context(
    task_type: TaskType = TaskType.GENERAL_CHAT,
    requires_citations: bool = False,
    expected_format: str = "text",
    risk: RiskLevel = RiskLevel.LOW,
    estimated_output_tokens: int = 100,
    schema: Dict[str, Any] = None,
) -> RoutingContext:
    features = FeatureExtractionResult(
        request_id="test-ver-001",
        prompt="What is machine learning?",
        prompt_tokens_estimated=8,
        detected_task_types=[task_type],
        primary_task_type=task_type,
        has_code_block=task_type == TaskType.CODING,
        has_image=False,
        has_structured_output_requirement=expected_format != "text",
        requires_citations=requires_citations,
        expected_output_format=expected_format,
        detected_language="en",
        domain_keywords=["machine", "learning"],
        tool_schemas_provided=False,
    )
    complexity = ComplexityEstimationResult(
        request_id="test-ver-001",
        complexity_level=ComplexityLevel.SIMPLE,
        complexity_score=0.2,
        risk_level=risk,
        risk_score=0.1,
        requires_reasoning=False,
        requires_vision=False,
        requires_coding=task_type == TaskType.CODING,
        requires_long_context=False,
        estimated_output_tokens=estimated_output_tokens,
        domain="general",
    )
    confidence = ConfidenceEngineResult(
        request_id="test-ver-001",
        overall_confidence=0.8,
        local_can_handle=True,
        local_confidence=0.75,
        recommended_min_tier=ExecutionTier.LOCAL,
        force_escalate_to=None,
        confidence_reasoning="Test",
    )
    metadata = {}
    if schema:
        metadata["expected_schema"] = schema

    return RoutingContext(
        request_id="test-ver-001",
        features=features,
        complexity=complexity,
        confidence=confidence,
        original_messages=[{"role": "user", "content": "What is machine learning?"}],
        metadata=metadata,
    )


# ---------------------------------------------------------------------------
# COMPLETENESS CHECKER TESTS
# ---------------------------------------------------------------------------

class TestCompletenessChecker:
    _cfg = {"min_response_chars": 20, "max_response_chars": 50000, "min_sentences": 1}

    def test_passes_normal_response(self):
        strategy = CompletenessCheckerStrategy(self._cfg)
        ctx = _make_context()
        result = strategy.verify(ctx, "Machine learning is a subset of AI that enables computers to learn from data.", "local")
        assert result.passed

    def test_fails_empty_response(self):
        strategy = CompletenessCheckerStrategy(self._cfg)
        ctx = _make_context()
        result = strategy.verify(ctx, "", "local")
        assert not result.passed

    def test_fails_too_short(self):
        strategy = CompletenessCheckerStrategy(self._cfg)
        ctx = _make_context()
        result = strategy.verify(ctx, "OK", "local")
        assert not result.passed

    def test_fails_refusal(self):
        strategy = CompletenessCheckerStrategy(self._cfg)
        ctx = _make_context()
        result = strategy.verify(ctx, "I am unable to help with that request.", "local")
        assert not result.passed

    def test_always_runs(self):
        strategy = CompletenessCheckerStrategy(self._cfg)
        ctx = _make_context()
        assert strategy.should_run(ctx, "any", "local")


# ---------------------------------------------------------------------------
# HALLUCINATION DETECTOR TESTS
# ---------------------------------------------------------------------------

class TestHallucinationDetector:
    _cfg = {
        "repetition_ratio_threshold": 0.40,
        "ngram_size": 4,
        "contradiction_keywords": ["I'm not sure but"],
    }

    def test_passes_clean_response(self):
        strategy = HallucinationDetectorStrategy(self._cfg)
        ctx = _make_context()
        result = strategy.verify(ctx, "Machine learning uses algorithms to learn patterns from data. It is widely used in industry.", "local")
        assert result.passed

    def test_fails_on_repetition(self):
        strategy = HallucinationDetectorStrategy(self._cfg)
        ctx = _make_context()
        # Repeat the same phrase many times
        repetitive = ("machine learning uses data to learn patterns from examples. " * 10).strip()
        result = strategy.verify(ctx, repetitive, "local")
        assert not result.passed
        assert result.metadata["repetition_ratio"] > 0.40

    def test_fails_on_contradiction_keyword(self):
        strategy = HallucinationDetectorStrategy(self._cfg)
        ctx = _make_context()
        result = strategy.verify(ctx, "I'm not sure but machine learning might be related to AI.", "local")
        assert not result.passed


# ---------------------------------------------------------------------------
# FORMAT VALIDATOR TESTS
# ---------------------------------------------------------------------------

class TestFormatValidator:
    _cfg = {"max_length_multiplier": 3.0, "min_length_fraction": 0.10}

    def test_passes_reasonable_length(self):
        strategy = FormatValidatorStrategy(self._cfg)
        # estimated_output_tokens=100 → expected_chars ≈ 400
        ctx = _make_context(estimated_output_tokens=100)
        response = "A" * 200  # Within expected range
        result = strategy.verify(ctx, response, "local")
        assert result.passed

    def test_fails_unclosed_fence(self):
        strategy = FormatValidatorStrategy(self._cfg)
        ctx = _make_context(expected_format="markdown", estimated_output_tokens=50)
        response = "Here is code:\n```python\ndef hello(): pass\n"  # No closing fence
        result = strategy.verify(ctx, response, "local")
        assert not result.passed
        assert any("fence" in r.lower() for r in result.failure_reasons)


# ---------------------------------------------------------------------------
# SCHEMA VALIDATOR TESTS
# ---------------------------------------------------------------------------

class TestSchemaValidator:
    _cfg = {"run_if_formats": ["json", "structured"], "strict_mode": True}

    def test_passes_valid_json(self):
        strategy = SchemaValidatorStrategy(self._cfg)
        ctx = _make_context(expected_format="json")
        result = strategy.verify(ctx, '{"name": "Alice", "age": 30}', "local")
        assert result.passed

    def test_fails_invalid_json(self):
        strategy = SchemaValidatorStrategy(self._cfg)
        ctx = _make_context(expected_format="json")
        result = strategy.verify(ctx, "This is not JSON at all", "local")
        assert not result.passed

    def test_extracts_from_fence(self):
        strategy = SchemaValidatorStrategy(self._cfg)
        ctx = _make_context(expected_format="json")
        response = '```json\n{"key": "value"}\n```'
        result = strategy.verify(ctx, response, "local")
        assert result.passed

    def test_skips_for_text_format(self):
        strategy = SchemaValidatorStrategy(self._cfg)
        ctx = _make_context(expected_format="text")
        assert not strategy.should_run(ctx, "any response", "local")


# ---------------------------------------------------------------------------
# CITATION VALIDATOR TESTS
# ---------------------------------------------------------------------------

class TestCitationValidator:
    _cfg = {"run_only_if_required": True, "min_citations": 1}

    def test_skips_when_not_required(self):
        strategy = CitationValidatorStrategy(self._cfg)
        ctx = _make_context(requires_citations=False)
        assert not strategy.should_run(ctx, "any", "local")

    def test_runs_when_required(self):
        strategy = CitationValidatorStrategy(self._cfg)
        ctx = _make_context(requires_citations=True)
        assert strategy.should_run(ctx, "any", "local")

    def test_passes_with_numbered_citation(self):
        strategy = CitationValidatorStrategy(self._cfg)
        ctx = _make_context(requires_citations=True)
        result = strategy.verify(ctx, "Machine learning is effective [1].", "local")
        assert result.passed

    def test_fails_without_citation(self):
        strategy = CitationValidatorStrategy(self._cfg)
        ctx = _make_context(requires_citations=True)
        result = strategy.verify(ctx, "Machine learning is effective.", "local")
        assert not result.passed


# ---------------------------------------------------------------------------
# CODE VALIDATOR TESTS
# ---------------------------------------------------------------------------

class TestCodeValidator:
    _cfg = {
        "run_if_task_types": ["CODING"],
        "run_unit_tests": False,
        "syntax_check_languages": ["python"],
        "execution_timeout_seconds": 5,
    }

    def test_passes_valid_python(self):
        strategy = CodeValidatorStrategy(self._cfg)
        ctx = _make_context(task_type=TaskType.CODING)
        response = "```python\ndef hello():\n    return 'world'\n```"
        result = strategy.verify(ctx, response, "local")
        assert result.passed

    def test_fails_invalid_python(self):
        strategy = CodeValidatorStrategy(self._cfg)
        ctx = _make_context(task_type=TaskType.CODING)
        response = "```python\ndef hello(\n    return 'world'\n```"  # Syntax error
        result = strategy.verify(ctx, response, "local")
        assert not result.passed

    def test_skips_for_non_coding(self):
        strategy = CodeValidatorStrategy(self._cfg)
        ctx = _make_context(task_type=TaskType.GENERAL_CHAT)
        assert not strategy.should_run(ctx, "any", "local")


# ---------------------------------------------------------------------------
# VERIFIER ORCHESTRATOR TESTS
# ---------------------------------------------------------------------------

class TestVerifier:
    def test_passes_good_response(self):
        verifier = Verifier(VERIFIER_CONFIG_PATH, inference_fn=None)
        ctx = _make_context()
        result = verifier.verify(
            ctx,
            "Machine learning is a method of data analysis that automates analytical model building.",
            "local",
        )
        assert result.status.value in ("PASSED", "PARTIAL")
        assert result.overall_score > 0.0

    def test_fails_empty_response(self):
        verifier = Verifier(VERIFIER_CONFIG_PATH, inference_fn=None)
        ctx = _make_context()
        result = verifier.verify(ctx, "", "local")
        assert result.status.value == "FAILED"
        assert len(result.failure_reasons) > 0

    def test_strategies_run_recorded(self):
        verifier = Verifier(VERIFIER_CONFIG_PATH, inference_fn=None)
        ctx = _make_context()
        result = verifier.verify(
            ctx, "Machine learning processes data to find patterns.", "local"
        )
        assert len(result.strategies_run) > 0

    def test_request_id_propagated(self):
        verifier = Verifier(VERIFIER_CONFIG_PATH, inference_fn=None)
        ctx = _make_context()
        result = verifier.verify(ctx, "Some response text here.", "local")
        assert result.request_id == ctx.request_id

    def test_escalation_recommended_on_failure(self):
        verifier = Verifier(VERIFIER_CONFIG_PATH, inference_fn=None)
        ctx = _make_context()
        result = verifier.verify(ctx, "", "local")
        assert result.recommended_escalation
        assert result.recommended_escalation_reason is not None
