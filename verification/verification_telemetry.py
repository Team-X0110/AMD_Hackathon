"""
verification/verification_telemetry.py
=======================================
Structured metrics emitter for the Local Verifier.

Populates verification-specific fields of an ExecutionRecord and emits
structured log entries for every verification pass.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from core.types import VerificationResult, RoutingContext
from telemetry.execution_record import ExecutionRecord

logger = logging.getLogger(__name__)


class VerificationTelemetry:
    """
    Emits structured verification metrics and updates ExecutionRecord fields.

    Usage:
        vt = VerificationTelemetry()
        vt.update_record(record, context, result, latency_ms)
        store.append(record)
    """

    def update_record(
        self,
        record: ExecutionRecord,
        context: RoutingContext,
        result: VerificationResult,
        verification_latency_ms: float,
    ) -> None:
        """
        Fill in verification fields on an existing ExecutionRecord in-place.

        Args:
            record: The ExecutionRecord produced by RoutingTelemetry.build_record().
            context: Routing context (for request_id correlation).
            result: The VerificationResult to record.
            verification_latency_ms: Elapsed time for the verification pass (ms).
        """
        record.verification_status = result.status.value
        record.verification_score = round(result.overall_score, 4)
        record.verification_confidence = round(result.overall_confidence, 4)
        record.strategies_run = result.strategies_run
        record.strategy_scores = {
            sr.strategy_name: round(sr.score, 4)
            for sr in result.strategy_results
        }
        record.verification_failure_reasons = result.failure_reasons
        record.recommended_escalation = result.recommended_escalation
        record.verification_latency_ms = round(verification_latency_ms, 2)

        self._emit_verification_log(context, result, verification_latency_ms)

    def emit_strategy_skip(
        self,
        context: RoutingContext,
        strategy_name: str,
        reason: str,
    ) -> None:
        """Emit a debug log when a strategy is skipped."""
        logger.debug(
            "verification_strategy_skipped",
            extra={
                "request_id": context.request_id,
                "strategy": strategy_name,
                "reason": reason,
            },
        )

    # ------------------------------------------------------------------
    # PRIVATE HELPERS
    # ------------------------------------------------------------------

    def _emit_verification_log(
        self,
        context: RoutingContext,
        result: VerificationResult,
        latency_ms: float,
    ) -> None:
        """Emit a structured INFO log for the verification result."""
        log_level = logging.INFO if result.status.value == "PASSED" else logging.WARNING
        logger.log(
            log_level,
            "verification_complete",
            extra={
                "request_id": context.request_id,
                "status": result.status.value,
                "score": round(result.overall_score, 4),
                "confidence": round(result.overall_confidence, 4),
                "strategies_run": result.strategies_run,
                "failure_count": len(result.failure_reasons),
                "recommended_escalation": result.recommended_escalation,
                "model_verified": result.model_id_verified,
                "latency_ms": round(latency_ms, 2),
            },
        )
        if result.failure_reasons:
            logger.warning(
                "verification_failures",
                extra={
                    "request_id": context.request_id,
                    "failures": result.failure_reasons,
                },
            )
