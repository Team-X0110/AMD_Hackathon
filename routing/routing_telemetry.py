"""
routing/routing_telemetry.py
=============================
Structured metrics emitter for Routing Engine decisions.

Populates the routing-specific fields of an ExecutionRecord and emits
structured log entries for every routing decision.  Does NOT do any I/O
to the telemetry JSONL file itself — that is the TelemetryStore's job.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from core.types import CandidateScore, RoutingDecision, RoutingContext
from telemetry.execution_record import ExecutionRecord

logger = logging.getLogger(__name__)


class RoutingTelemetry:
    """
    Emits structured routing metrics.

    Usage:
        telemetry = RoutingTelemetry()
        record = telemetry.build_record(context, decision, latency_ms)
        store.append(record)
    """

    def build_record(
        self,
        context: RoutingContext,
        decision: RoutingDecision,
        routing_latency_ms: float,
    ) -> ExecutionRecord:
        """
        Create an ExecutionRecord pre-populated with routing phase data.

        Verification and reflection fields are left at their zero-value
        defaults — downstream modules fill them in before final append.

        Args:
            context: The routing context.
            decision: The RoutingDecision produced by the engine.
            routing_latency_ms: Wall-clock time for the routing decision (ms).

        Returns:
            Partially-populated ExecutionRecord.
        """
        rankings = self._build_rankings(decision.all_candidates)

        record = ExecutionRecord(
            request_id=context.request_id,
            # Routing fields
            chosen_model_id=decision.selected_model_id,
            chosen_model_display_name=decision.selected_model_display_name,
            chosen_tier=decision.selected_tier.value,
            is_local=decision.is_local,
            candidate_rankings=rankings,
            routing_rationale=decision.routing_rationale,
            escalation_tier_at_route=decision.escalation_tier_attempted,
            estimated_cost_usd_at_route=decision.estimated_cost_usd,
            # Task feature fields
            primary_task_type=context.features.primary_task_type.value,
            complexity_level=context.complexity.complexity_level.value,
            risk_level=context.complexity.risk_level.value,
            complexity_score=context.complexity.complexity_score,
            risk_score=context.complexity.risk_score,
            overall_confidence=context.confidence.overall_confidence,
            prompt_tokens_estimated=context.features.prompt_tokens_estimated,
            estimated_output_tokens=context.complexity.estimated_output_tokens,
            has_image=context.features.has_image,
            requires_coding=context.complexity.requires_coding,
            requires_reasoning=context.complexity.requires_reasoning,
            # Latency
            routing_latency_ms=routing_latency_ms,
        )

        self._emit_routing_log(context, decision, routing_latency_ms)
        return record

    def emit_escalation(
        self,
        context: RoutingContext,
        from_tier: str,
        to_tier: str,
        reason: str,
    ) -> None:
        """
        Emit a structured log entry when a tier escalation occurs.

        Args:
            context: Routing context.
            from_tier: Tier label being escalated from.
            to_tier: Tier label being escalated to.
            reason: Human-readable escalation reason.
        """
        logger.info(
            "routing_escalation",
            extra={
                "request_id": context.request_id,
                "from_tier": from_tier,
                "to_tier": to_tier,
                "reason": reason,
                "task_type": context.features.primary_task_type.value,
                "complexity": context.complexity.complexity_level.value,
            },
        )

    # ------------------------------------------------------------------
    # PRIVATE HELPERS
    # ------------------------------------------------------------------

    def _build_rankings(
        self,
        candidates: List[CandidateScore],
    ) -> List[Dict[str, Any]]:
        """Serialise candidate rankings to a list of dicts for the record."""
        return [
            {
                "model_id": c.model_id,
                "display_name": c.display_name,
                "tier": c.routing_tier,
                "utility_score": round(c.utility_score, 4),
                "estimated_cost_usd": round(c.estimated_cost_usd, 8),
                "qualified": c.meets_capability_requirements,
                "disqualification_reasons": c.disqualification_reasons,
            }
            for c in candidates
        ]

    def _emit_routing_log(
        self,
        context: RoutingContext,
        decision: RoutingDecision,
        latency_ms: float,
    ) -> None:
        """Emit a structured INFO log for the routing decision."""
        logger.info(
            "routing_decision",
            extra={
                "request_id": context.request_id,
                "selected_model": decision.selected_model_id,
                "selected_tier": decision.selected_tier.value,
                "is_local": decision.is_local,
                "utility_score": round(decision.utility_score, 4),
                "estimated_cost_usd": round(decision.estimated_cost_usd, 8),
                "escalation_tier": decision.escalation_tier_attempted,
                "latency_ms": round(latency_ms, 2),
                "task_type": context.features.primary_task_type.value,
                "complexity": context.complexity.complexity_level.value,
                "confidence": round(context.confidence.overall_confidence, 4),
            },
        )
