"""
verification/strategies/format_validator.py
============================================
Validates that the response length and format are within expected bounds.

Checks:
1. Response length relative to expected output tokens (from ComplexityEstimation).
2. Output format matches the expected_output_format from FeatureExtraction.
3. For markdown: checks for unclosed code fences.
4. Response does not begin with apologetic / meta preamble.

No LLM calls are made.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List

from core.types import RoutingContext, StrategyResult
from verification.strategies.base_strategy import BaseVerificationStrategy

logger = logging.getLogger(__name__)

# Approx tokens → chars conversion factor (GPT-style tokenisation heuristic)
_CHARS_PER_TOKEN = 4.0

# Patterns that indicate the model is talking about itself rather than answering
_META_PREAMBLE_PATTERNS = [
    re.compile(r"^(as an ai|as a language model|as an artificial intelligence)", re.I),
    re.compile(r"^(great question|certainly!|of course!|absolutely!)\s*\n", re.I),
    re.compile(r"^i'll (help|assist|answer) you (with )?", re.I),
]

# Unclosed code fence detector
_FENCE_OPEN = re.compile(r"^```", re.MULTILINE)


class FormatValidatorStrategy(BaseVerificationStrategy):
    """
    Response format and length sanity checker.

    Args:
        config: Strategy config from verifier_config.yaml.
    """

    def __init__(self, config: Dict[str, Any]) -> None:
        super().__init__(config)
        self._name = "format_validator"
        self._max_length_multiplier: float = float(
            config.get("max_length_multiplier", 3.0)
        )
        self._min_length_fraction: float = float(
            config.get("min_length_fraction", 0.10)
        )

    def should_run(
        self,
        context: RoutingContext,
        response: str,
        model_id: str,
    ) -> bool:
        """Always runs — format is a universal quality signal."""
        return True

    def _run_check(
        self,
        context: RoutingContext,
        response: str,
        model_id: str,
    ) -> StrategyResult:
        """Check response length and format markers."""
        failure_reasons: List[str] = []
        metadata: Dict[str, Any] = {}

        resp_chars = len(response.strip())
        expected_tokens = context.complexity.estimated_output_tokens
        expected_chars = expected_tokens * _CHARS_PER_TOKEN

        metadata["response_chars"] = resp_chars
        metadata["expected_chars"] = expected_chars
        metadata["expected_output_tokens"] = expected_tokens

        # --- Length bounds ---
        max_chars = expected_chars * self._max_length_multiplier
        min_chars = expected_chars * self._min_length_fraction

        if expected_chars > 0:
            if resp_chars > max_chars:
                failure_reasons.append(
                    f"Response is too long: {resp_chars} chars "
                    f"(expected ≤ {int(max_chars)}, "
                    f"multiplier: {self._max_length_multiplier}x)"
                )
            elif resp_chars < min_chars:
                failure_reasons.append(
                    f"Response may be truncated: {resp_chars} chars "
                    f"(expected ≥ {int(min_chars)}, "
                    f"fraction: {self._min_length_fraction}x)"
                )

        length_ratio = (resp_chars / expected_chars) if expected_chars > 0 else 1.0
        metadata["length_ratio"] = round(length_ratio, 3)

        # --- Format-specific checks ---
        expected_format = context.features.expected_output_format.lower()

        if expected_format == "json":
            stripped = response.strip()
            if not (
                (stripped.startswith("{") and stripped.endswith("}"))
                or (stripped.startswith("[") and stripped.endswith("]"))
                or "```json" in response.lower()
            ):
                failure_reasons.append(
                    "Expected JSON output but response does not appear to be JSON"
                )

        elif expected_format in ("code", "markdown"):
            # Check for unclosed code fences
            fence_count = len(_FENCE_OPEN.findall(response))
            metadata["fence_count"] = fence_count
            if fence_count % 2 != 0:
                failure_reasons.append(
                    f"Unclosed code fence detected ({fence_count} '```' markers)"
                )

        # --- Meta preamble detection ---
        has_preamble = any(p.search(response.strip()) for p in _META_PREAMBLE_PATTERNS)
        metadata["has_meta_preamble"] = has_preamble
        if has_preamble:
            failure_reasons.append(
                "Response begins with AI self-reference preamble instead of direct answer"
            )

        # Score: start at 1.0, deduct per issue
        score = 1.0
        if length_ratio > self._max_length_multiplier:
            overage = length_ratio / self._max_length_multiplier
            score = max(0.0, score - (overage - 1.0) * 0.5)
        elif length_ratio < self._min_length_fraction and expected_chars > 100:
            score = max(0.0, length_ratio / self._min_length_fraction * 0.5)

        if has_preamble:
            score = max(0.0, score - 0.15)

        score = max(0.0, score - len(failure_reasons) * 0.20)
        passed = len(failure_reasons) == 0

        return self._make_result(
            passed=passed,
            score=score,
            confidence=0.80,
            failure_reasons=failure_reasons,
            metadata=metadata,
        )
