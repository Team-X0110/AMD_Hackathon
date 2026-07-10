"""
reflection/failure_classifier.py
==================================
Classifies WHY a verification failed into a FailureCategory.

The classifier applies a priority-ordered decision tree across the
VerificationResult's strategy_results and failure_reasons.  It returns
the single most specific category that best describes the primary failure.

Priority order (most specific → most general):
    1. UNSAFE_OUTPUT      — detected by refusal/safety patterns
    2. INCORRECT_SCHEMA   — schema_validator explicitly failed
    3. POOR_CODE_QUALITY  — code_validator explicitly failed
    4. HALLUCINATION      — hallucination_detector explicitly failed
    5. FORMATTING         — format_validator explicitly failed
    6. MISSING_INFORMATION— completeness_checker failed on keyword overlap
    7. INSUFFICIENT_REASONING — low score + reasoning task
    8. TOOL_FAILURE       — tool-calling task context + low score
    9. LOW_CONFIDENCE     — verifier overall confidence below threshold
   10. EXECUTION_FAILURE  — catch-all for strategy exceptions
   11. UNKNOWN            — fallback

No LLM calls are made.
"""

from __future__ import annotations

import logging
import re
from typing import List

from core.interfaces import IFailureClassifier
from core.types import (
    FailureCategory,
    RiskLevel,
    RoutingContext,
    TaskType,
    VerificationResult,
    VerificationStatus,
)

logger = logging.getLogger(__name__)

# Unsafe content indicators (simple keyword heuristics)
_UNSAFE_PATTERNS = [
    re.compile(r"\b(how to (make|build|create|synthesize) (a )?bomb|explosive|weapon)\b", re.I),
    re.compile(r"\b(malware|ransomware|keylogger|exploit (kit|code))\b", re.I),
    re.compile(r"\b(child (sexual|pornography|abuse))\b", re.I),
    re.compile(r"\b(suicide (method|instruction|guide|how to))\b", re.I),
]


class FailureClassifier(IFailureClassifier):
    """
    Determines the primary FailureCategory from a failed VerificationResult.

    Args:
        confidence_threshold: If overall_confidence falls below this, classify
            as LOW_CONFIDENCE.  Should match verifier config escalation threshold.
    """

    def __init__(self, confidence_threshold: float = 0.55) -> None:
        self._confidence_threshold = confidence_threshold

    def classify(
        self,
        verification_result: VerificationResult,
        context: RoutingContext,
        response: str,
    ) -> FailureCategory:
        """
        Classify the primary failure category.

        Args:
            verification_result: The failed VerificationResult.
            context: Full routing context.
            response: The model response that failed verification.

        Returns:
            Most specific FailureCategory.
        """
        if verification_result.status == VerificationStatus.PASSED:
            logger.debug(
                "failure_classifier_called_on_pass",
                extra={"request_id": context.request_id},
            )
            return FailureCategory.UNKNOWN

        failed_strategies = {
            sr.strategy_name
            for sr in verification_result.strategy_results
            if not sr.passed
        }
        all_reasons = " ".join(verification_result.failure_reasons).lower()

        # 1. Unsafe content check (highest priority — always abort)
        if self._is_unsafe(response, context):
            logger.warning(
                "failure_classified_unsafe",
                extra={"request_id": context.request_id},
            )
            return FailureCategory.UNSAFE_OUTPUT

        # 2. Schema failure
        if "schema_validator" in failed_strategies:
            return FailureCategory.INCORRECT_SCHEMA

        # 3. Code quality failure
        if "code_validator" in failed_strategies:
            return FailureCategory.POOR_CODE_QUALITY

        # 4. Hallucination signals
        if "hallucination_detector" in failed_strategies:
            return FailureCategory.HALLUCINATION

        # 5. Formatting failure
        if "format_validator" in failed_strategies:
            return FailureCategory.FORMATTING

        # 6. Missing information / incomplete
        if "completeness_checker" in failed_strategies:
            if "overlap" in all_reasons or "missing" in all_reasons:
                return FailureCategory.MISSING_INFORMATION
            return FailureCategory.MISSING_INFORMATION

        # 7. Insufficient reasoning (task required reasoning but score is low)
        if (
            context.complexity.requires_reasoning
            and verification_result.overall_score < 0.5
        ):
            return FailureCategory.INSUFFICIENT_REASONING

        # 8. Tool failure (tool-calling task with any strategy failure)
        if context.features.primary_task_type in (
            TaskType.TOOL_CALLING,
            TaskType.AGENTS,
        ) and failed_strategies:
            return FailureCategory.TOOL_FAILURE

        # 9. Low confidence
        if verification_result.overall_confidence < self._confidence_threshold:
            return FailureCategory.LOW_CONFIDENCE

        # 10. Strategy exception (any strategy produced an exception message)
        if any("raised exception" in r.lower() for r in verification_result.failure_reasons):
            return FailureCategory.EXECUTION_FAILURE

        # 11. Fallback
        logger.debug(
            "failure_classified_unknown",
            extra={
                "request_id": context.request_id,
                "failed_strategies": list(failed_strategies),
            },
        )
        return FailureCategory.UNKNOWN

    # ------------------------------------------------------------------
    # PRIVATE HELPERS
    # ------------------------------------------------------------------

    def _is_unsafe(self, response: str, context: RoutingContext) -> bool:
        """Check for unsafe content using heuristic patterns."""
        # Critical risk context + any safety-related failure reason
        if context.complexity.risk_level == RiskLevel.CRITICAL:
            safety_keywords = {"unsafe", "harmful", "dangerous", "violat", "prohibit"}
            reasons_text = " ".join(context.confidence.confidence_reasoning.lower().split())
            if any(kw in reasons_text for kw in safety_keywords):
                return True

        # Direct pattern match in response
        for pattern in _UNSAFE_PATTERNS:
            if pattern.search(response):
                return True

        return False
