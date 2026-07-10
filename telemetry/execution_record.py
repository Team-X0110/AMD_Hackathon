"""
telemetry/execution_record.py
==============================
Per-request execution record that captures the full lifecycle of a single
pipeline run — from routing decision through verification and reflection.

Every field is designed to support future online learning:
- Model selection quality can be inferred from (chosen_model, verification_score).
- Escalation patterns emerge from (retry_count, escalation_count, final_tier).
- Cost efficiency is tracked via (estimated_tokens, actual_tokens, total_cost_usd).
"""

from __future__ import annotations

import dataclasses
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class ExecutionRecord:
    """
    Complete telemetry record for one pipeline execution.

    Designed to be serialised as a single JSON line in the JSONL telemetry file.
    All fields use JSON-native types (str, int, float, bool, list, dict, None).

    Attributes:
        request_id: UUID-v4 correlation key — links logs, traces, and records.
        session_id: Optional grouping key for multi-turn conversations.

        -- ROUTING --
        chosen_model_id: Model selected by the Routing Engine.
        chosen_model_display_name: Human-readable model name.
        chosen_tier: ExecutionTier label of the selected model.
        is_local: True if the local Ollama model was chosen.
        candidate_rankings: List of {model_id, utility_score, tier} for all scored candidates.
        routing_rationale: Human-readable explanation from RoutingDecision.
        escalation_tier_at_route: Tier order attempted when the final decision was made.
        estimated_cost_usd_at_route: Cost estimate at routing time.

        -- TASK FEATURES --
        primary_task_type: TaskType enum value as string.
        complexity_level: ComplexityLevel string.
        risk_level: RiskLevel string.
        complexity_score: [0.0, 1.0].
        risk_score: [0.0, 1.0].
        overall_confidence: Confidence engine output [0.0, 1.0].
        prompt_tokens_estimated: Estimated input tokens.
        estimated_output_tokens: Estimated output tokens.
        has_image: Whether the request included an image.
        requires_coding: Whether coding was required.
        requires_reasoning: Whether reasoning was required.

        -- VERIFICATION --
        verification_status: "PASSED" | "FAILED" | "PARTIAL" | "SKIPPED".
        verification_score: Overall score [0.0, 1.0].
        verification_confidence: Overall confidence [0.0, 1.0].
        strategies_run: List of strategy names that executed.
        strategy_scores: Dict of strategy_name → score.
        verification_failure_reasons: List of failure reason strings.
        recommended_escalation: Whether verifier recommended escalation.

        -- REFLECTION --
        reflection_triggered: True if the Reflection Agent ran.
        reflection_succeeded: True if reflection produced an accepted answer.
        total_retries: Total retry attempts by the Reflection Agent.
        total_escalations: Number of tier escalations performed.
        failure_categories_seen: List of FailureCategory strings encountered.
        abort_reason: Why the agent aborted (if applicable).
        execution_path: Ordered list of (model_id, action) pairs describing the path.

        -- TOKENS & COST --
        estimated_tokens_total: Total estimated tokens across all attempts.
        actual_tokens_total: Actual tokens used (from API response, if available).
        total_cost_usd: Total dollar cost across all Fireworks calls.
        local_calls_made: Number of Ollama calls made.
        fireworks_calls_made: Number of Fireworks API calls made.

        -- LATENCY --
        routing_latency_ms: Time spent in the Routing Engine (ms).
        verification_latency_ms: Time spent in the Verifier (ms).
        reflection_latency_ms: Time spent in the Reflection Agent (ms).
        total_latency_ms: Wall-clock total for the full pipeline (ms).

        -- OUTCOME --
        final_response_length: Character count of the accepted response.
        final_model_id: Model that produced the accepted final response.
        final_tier: ExecutionTier of the final model.
        pipeline_succeeded: True if a verified response was returned to the caller.

        -- METADATA --
        record_timestamp: ISO-8601 UTC timestamp when the record was created.
        schema_version: Record schema version for forward compatibility.
        extra: Free-form dict for any additional fields added by downstream modules.
    """

    # Identifiers
    request_id: str
    session_id: Optional[str] = None

    # Routing
    chosen_model_id: str = ""
    chosen_model_display_name: str = ""
    chosen_tier: str = ""
    is_local: bool = False
    candidate_rankings: List[Dict[str, Any]] = field(default_factory=list)
    routing_rationale: str = ""
    escalation_tier_at_route: int = 0
    estimated_cost_usd_at_route: float = 0.0

    # Task features
    primary_task_type: str = ""
    complexity_level: str = ""
    risk_level: str = ""
    complexity_score: float = 0.0
    risk_score: float = 0.0
    overall_confidence: float = 0.0
    prompt_tokens_estimated: int = 0
    estimated_output_tokens: int = 0
    has_image: bool = False
    requires_coding: bool = False
    requires_reasoning: bool = False

    # Verification
    verification_status: str = "SKIPPED"
    verification_score: float = 0.0
    verification_confidence: float = 0.0
    strategies_run: List[str] = field(default_factory=list)
    strategy_scores: Dict[str, float] = field(default_factory=dict)
    verification_failure_reasons: List[str] = field(default_factory=list)
    recommended_escalation: bool = False

    # Reflection
    reflection_triggered: bool = False
    reflection_succeeded: bool = False
    total_retries: int = 0
    total_escalations: int = 0
    failure_categories_seen: List[str] = field(default_factory=list)
    abort_reason: Optional[str] = None
    execution_path: List[Dict[str, str]] = field(default_factory=list)

    # Tokens & cost
    estimated_tokens_total: int = 0
    actual_tokens_total: Optional[int] = None
    total_cost_usd: float = 0.0
    local_calls_made: int = 0
    fireworks_calls_made: int = 0

    # Latency (ms)
    routing_latency_ms: float = 0.0
    verification_latency_ms: float = 0.0
    reflection_latency_ms: float = 0.0
    total_latency_ms: float = 0.0

    # Outcome
    final_response_length: int = 0
    final_model_id: str = ""
    final_tier: str = ""
    pipeline_succeeded: bool = False

    # Metadata
    record_timestamp: str = field(default_factory=_now_utc)
    schema_version: str = "1.0"
    extra: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Serialise to a JSON-compatible dict."""
        return dataclasses.asdict(self)

    def to_json_line(self) -> str:
        """Serialise to a single JSON line for JSONL append."""
        return json.dumps(self.to_dict(), ensure_ascii=False, default=str)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ExecutionRecord":
        """Deserialise from a dict (e.g. a parsed JSONL line)."""
        known = {f.name for f in dataclasses.fields(cls)}
        extra = {k: v for k, v in data.items() if k not in known}
        filtered = {k: v for k, v in data.items() if k in known}
        record = cls(**filtered)
        record.extra.update(extra)
        return record
