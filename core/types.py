"""
core/types.py
=============
Canonical shared dataclasses and enumerations for the AMD Hackathon
multi-agent orchestration framework.

All modules import from here.  This file has NO project-level imports —
it only uses stdlib, making it safe as the root of the dependency tree.

Design notes:
- All float scores are stored normalised to [0.0, 1.0].
- All timestamps are ISO-8601 UTC strings (datetime.utcnow().isoformat() + "Z").
- request_id (UUID-v4) flows unchanged through every module and telemetry record.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------------------

def _now_utc() -> str:
    """Return current UTC time as an ISO-8601 string."""
    return datetime.now(timezone.utc).isoformat()


def new_request_id() -> str:
    """Generate a new UUID-v4 request identifier."""
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# ENUMERATIONS
# ---------------------------------------------------------------------------

class TaskType(str, Enum):
    """Supported task categories.  A prompt may map to multiple types."""
    CODING          = "CODING"
    REASONING       = "REASONING"
    VISION          = "VISION"
    GENERAL_CHAT    = "GENERAL_CHAT"
    MATHEMATICS     = "MATHEMATICS"
    SQL             = "SQL"
    TRANSLATION     = "TRANSLATION"
    SUMMARIZATION   = "SUMMARIZATION"
    CLASSIFICATION  = "CLASSIFICATION"
    EXTRACTION      = "EXTRACTION"
    DOCUMENT_QA     = "DOCUMENT_QA"
    RAG             = "RAG"
    RESEARCH        = "RESEARCH"
    CREATIVE_WRITING = "CREATIVE_WRITING"
    TOOL_CALLING    = "TOOL_CALLING"
    AGENTS          = "AGENTS"


class ComplexityLevel(str, Enum):
    """Task complexity band.  Maps to routing tier minimum."""
    SIMPLE  = "Simple"
    MEDIUM  = "Medium"
    COMPLEX = "Complex"
    EXPERT  = "Expert"


class RiskLevel(str, Enum):
    """Risk / safety level of the request."""
    LOW      = "low"
    MEDIUM   = "medium"
    HIGH     = "high"
    CRITICAL = "critical"


class ExecutionTier(str, Enum):
    """Model execution tier, ordered cheapest → most expensive."""
    LOCAL         = "LOCAL"
    CHEAP         = "CHEAP"
    BALANCED      = "BALANCED"
    PREMIUM       = "PREMIUM"
    ULTRA_PREMIUM = "ULTRA_PREMIUM"


class VerificationStatus(str, Enum):
    """Aggregate verification outcome."""
    PASSED  = "PASSED"
    FAILED  = "FAILED"
    PARTIAL = "PARTIAL"
    SKIPPED = "SKIPPED"


class FailureCategory(str, Enum):
    """Why verification failed — drives the Reflection Agent's action."""
    INSUFFICIENT_REASONING = "INSUFFICIENT_REASONING"
    HALLUCINATION          = "HALLUCINATION"
    FORMATTING             = "FORMATTING"
    INCORRECT_SCHEMA       = "INCORRECT_SCHEMA"
    MISSING_INFORMATION    = "MISSING_INFORMATION"
    UNSAFE_OUTPUT          = "UNSAFE_OUTPUT"
    TOOL_FAILURE           = "TOOL_FAILURE"
    LOW_CONFIDENCE         = "LOW_CONFIDENCE"
    POOR_CODE_QUALITY      = "POOR_CODE_QUALITY"
    EXECUTION_FAILURE      = "EXECUTION_FAILURE"
    UNKNOWN                = "UNKNOWN"


class ReflectionAction(str, Enum):
    """Action the Reflection Agent may take after classifying a failure."""
    RETRY_SAME_COT       = "RETRY_SAME_COT"
    RETRY_SAME_GROUNDING = "RETRY_SAME_GROUNDING"
    RETRY_SAME_FORMAT    = "RETRY_SAME_FORMAT"
    RETRY_SAME_SCHEMA    = "RETRY_SAME_SCHEMA"
    RETRY_WITH_CONTEXT   = "RETRY_WITH_CONTEXT"
    ABORT                = "ABORT"
    RETRY_TOOL_SIMPLIFY  = "RETRY_TOOL_SIMPLIFY"
    ESCALATE             = "ESCALATE"
    RETRY_CODING_MODEL   = "RETRY_CODING_MODEL"
    ESCALATE_AFTER_RETRY = "ESCALATE_AFTER_RETRY"


# ---------------------------------------------------------------------------
# UPSTREAM MODULE OUTPUT TYPES
# Produced by Feature Extractor, Complexity Estimator, Confidence Engine.
# See sampleform.txt for the full contract.
# ---------------------------------------------------------------------------

@dataclass
class FeatureExtractionResult:
    """
    Standardized output from the Feature Extractor module.

    Attributes:
        request_id: UUID-v4 shared across the entire pipeline.
        prompt: Raw user prompt, unmodified.
        prompt_tokens_estimated: Token count estimate (heuristic or tiktoken).
        detected_task_types: All TaskType values detected in the prompt.
        primary_task_type: Single highest-confidence task type.
        has_code_block: True if prompt contains a fenced code block.
        has_image: True if prompt contains an image reference.
        has_structured_output_requirement: True if response must be structured.
        requires_citations: True if the answer needs source citations.
        expected_output_format: One of "text", "json", "code", "markdown", "structured".
        detected_language: ISO-639-1 language code (e.g. "en", "zh").
        domain_keywords: Top extracted domain keywords from the prompt.
        tool_schemas_provided: True if tool/function schemas are in the prompt.
        extraction_timestamp: ISO-8601 UTC timestamp.
    """
    request_id: str
    prompt: str
    prompt_tokens_estimated: int
    detected_task_types: List[TaskType]
    primary_task_type: TaskType
    has_code_block: bool
    has_image: bool
    has_structured_output_requirement: bool
    requires_citations: bool
    expected_output_format: str
    detected_language: str
    domain_keywords: List[str]
    tool_schemas_provided: bool
    extraction_timestamp: str = field(default_factory=_now_utc)


@dataclass
class ComplexityEstimationResult:
    """
    Standardized output from the Complexity / Domain / Risk Estimator.

    Attributes:
        request_id: Same UUID-v4 as FeatureExtractionResult.
        complexity_level: Categorical complexity band.
        complexity_score: Continuous [0.0, 1.0] representation.
        risk_level: Safety / risk band.
        risk_score: Continuous [0.0, 1.0] representation.
        requires_reasoning: True if multi-step reasoning is needed.
        requires_vision: True if image understanding is needed.
        requires_coding: True if code generation/analysis is needed.
        requires_long_context: True if prompt exceeds ~16k tokens.
        estimated_output_tokens: Predicted response token length.
        domain: Domain string e.g. "software_engineering", "science".
        estimation_timestamp: ISO-8601 UTC timestamp.
    """
    request_id: str
    complexity_level: ComplexityLevel
    complexity_score: float
    risk_level: RiskLevel
    risk_score: float
    requires_reasoning: bool
    requires_vision: bool
    requires_coding: bool
    requires_long_context: bool
    estimated_output_tokens: int
    domain: str
    estimation_timestamp: str = field(default_factory=_now_utc)


@dataclass
class ConfidenceEngineResult:
    """
    Standardized output from the Confidence Engine.

    Attributes:
        request_id: Same UUID-v4 as upstream modules.
        overall_confidence: How confident the system is any model can satisfy
            this request. Range [0.0, 1.0].
        local_can_handle: True if the local Ollama model is expected to succeed.
        local_confidence: Estimated accuracy if handled locally. [0.0, 1.0].
        recommended_min_tier: Minimum ExecutionTier that should be used.
        force_escalate_to: If set, routing must jump directly to this tier;
            all cheaper tiers are skipped.
        confidence_reasoning: Human-readable explanation of the decision.
        estimation_timestamp: ISO-8601 UTC timestamp.
    """
    request_id: str
    overall_confidence: float
    local_can_handle: bool
    local_confidence: float
    recommended_min_tier: ExecutionTier
    force_escalate_to: Optional[ExecutionTier]
    confidence_reasoning: str
    estimation_timestamp: str = field(default_factory=_now_utc)


# ---------------------------------------------------------------------------
# ROUTING CONTEXT — aggregated input to the Routing Engine
# ---------------------------------------------------------------------------

@dataclass
class RoutingContext:
    """
    Fully aggregated context object passed into the Routing Engine.
    This is the canonical interface contract between upstream modules and
    modules 3.5 / 3.6 / 3.7.

    Attributes:
        request_id: UUID-v4 correlation key.
        features: Output of the Feature Extractor.
        complexity: Output of the Complexity / Risk Estimator.
        confidence: Output of the Confidence Engine.
        original_messages: OpenAI-compatible message list passed verbatim to
            the selected model.
        additional_context: Optional extra text injected on retry by the
            Reflection Agent.
        metadata: Free-form pass-through metadata for observability.
    """
    request_id: str
    features: FeatureExtractionResult
    complexity: ComplexityEstimationResult
    confidence: ConfidenceEngineResult
    original_messages: List[Dict[str, Any]]
    additional_context: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# ROUTING MODULE TYPES
# ---------------------------------------------------------------------------

@dataclass
class ModelProfile:
    """
    Normalized model profile loaded from models.json by ModelRegistry.
    All scores are normalised to [0.0, 1.0].

    Attributes:
        model_id: Full Fireworks model ID string.
        display_name: Human-readable model name.
        provider: Provider name.
        routing_tier: Tier label matching escalation_tiers in routing_config.yaml.
        tier_order: Numeric tier position (0=LOCAL … 4=ULTRA_PREMIUM).
        quality_score: Overall quality [0, 1].
        reasoning_score: Reasoning ability [0, 1].
        coding_score: Coding ability [0, 1].
        vision_score: Vision ability [0, 1] or None if no vision.
        token_efficiency_score: Token efficiency [0, 1].
        cost_score: Cost attractiveness [0, 1] — higher = cheaper.
        latency_score: Latency attractiveness [0, 1] — higher = faster.
        recommended_confidence_threshold: Min confidence for this model to be used.
        recommended_task_complexity: Complexity label this model targets.
        input_cost_per_million: $/million input tokens.
        output_cost_per_million: $/million output tokens.
        has_vision: Whether the model supports image inputs.
        context_window: Maximum context window in tokens.
        max_output_tokens: Maximum generation length in tokens.
        preferred_temperature: Recommended temperature.
        preferred_max_tokens: Recommended max_tokens parameter.
        preferred_prompt_style: Human-readable style guidance.
        agent_recommendations: Dict of task → score [0–10] from models.json.
        api_parameters: Dict of parameter_name → bool (supported or not).
        failure_modes: Known failure patterns.
        prompt_engineering_tips: Tips for best results with this model.
        latency_class: Raw latency class string from models.json.
    """
    model_id: str
    display_name: str
    provider: str
    routing_tier: str
    tier_order: int
    quality_score: float
    reasoning_score: float
    coding_score: float
    vision_score: Optional[float]
    token_efficiency_score: float
    cost_score: float
    latency_score: float
    recommended_confidence_threshold: float
    recommended_task_complexity: str
    input_cost_per_million: float
    output_cost_per_million: float
    has_vision: bool
    context_window: int
    max_output_tokens: int
    preferred_temperature: float
    preferred_max_tokens: int
    preferred_prompt_style: str
    agent_recommendations: Dict[str, Optional[float]]
    api_parameters: Dict[str, bool]
    failure_modes: Optional[str]
    prompt_engineering_tips: Optional[str]
    latency_class: str


@dataclass
class CandidateScore:
    """
    Scored representation of one model candidate.

    Attributes:
        model_id: Fireworks model ID.
        display_name: Human-readable name.
        routing_tier: Tier label.
        tier_order: Numeric tier.
        utility_score: Final weighted utility score [0, 1].
        score_breakdown: Component name → raw normalised score [0, 1].
        weighted_breakdown: Component name → weighted contribution.
        is_local: True if this is the local Ollama model.
        estimated_cost_usd: Estimated dollar cost for this request.
        meets_capability_requirements: False if disqualified.
        disqualification_reasons: Why the model was disqualified (if any).
    """
    model_id: str
    display_name: str
    routing_tier: str
    tier_order: int
    utility_score: float
    score_breakdown: Dict[str, float]
    weighted_breakdown: Dict[str, float]
    is_local: bool
    estimated_cost_usd: float
    meets_capability_requirements: bool
    disqualification_reasons: List[str]


@dataclass
class RoutingDecision:
    """
    Final output of the Routing Engine.

    Attributes:
        request_id: Correlation key.
        selected_model_id: Full model ID of the chosen model.
        selected_model_display_name: Human-readable name.
        selected_tier: ExecutionTier of the chosen model.
        is_local: True if Ollama was selected.
        utility_score: Final utility score of the winner.
        score_breakdown: Component scores of the winning candidate.
        all_candidates: All scored candidates, ranked by utility_score desc.
        escalation_tier_attempted: How many tiers were tried (0 = first attempt).
        estimated_cost_usd: Estimated cost for this call.
        api_parameters: Ready-to-use parameters dict for the API call.
        routing_rationale: Human-readable explanation of why this model was chosen.
        routing_timestamp: ISO-8601 UTC timestamp.
    """
    request_id: str
    selected_model_id: str
    selected_model_display_name: str
    selected_tier: ExecutionTier
    is_local: bool
    utility_score: float
    score_breakdown: Dict[str, float]
    all_candidates: List[CandidateScore]
    escalation_tier_attempted: int
    estimated_cost_usd: float
    api_parameters: Dict[str, Any]
    routing_rationale: str
    routing_timestamp: str = field(default_factory=_now_utc)


# ---------------------------------------------------------------------------
# VERIFICATION MODULE TYPES
# ---------------------------------------------------------------------------

@dataclass
class StrategyResult:
    """
    Result from a single verification strategy.

    Attributes:
        strategy_name: Unique name of the strategy.
        passed: True if the strategy considers the response acceptable.
        confidence: Strategy's confidence in its verdict [0.0, 1.0].
        score: Numeric quality score [0.0, 1.0].
        failure_reasons: List of human-readable failure descriptions.
        metadata: Strategy-specific diagnostic data.
    """
    strategy_name: str
    passed: bool
    confidence: float
    score: float
    failure_reasons: List[str]
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class VerificationResult:
    """
    Aggregated output of the Local Verifier.

    Attributes:
        request_id: Correlation key.
        status: Aggregate verdict (PASSED / FAILED / PARTIAL / SKIPPED).
        overall_confidence: Weighted aggregate confidence [0.0, 1.0].
        overall_score: Weighted aggregate score [0.0, 1.0].
        strategy_results: Individual result per strategy.
        failure_reasons: Consolidated list of all failure reasons.
        recommended_escalation: True if the verifier recommends escalation.
        recommended_escalation_reason: Why escalation is recommended.
        strategies_run: Names of strategies that were executed.
        strategies_skipped: Names of strategies that were skipped.
        verification_timestamp: ISO-8601 UTC timestamp.
        model_id_verified: The model whose response was verified.
    """
    request_id: str
    status: VerificationStatus
    overall_confidence: float
    overall_score: float
    strategy_results: List[StrategyResult]
    failure_reasons: List[str]
    recommended_escalation: bool
    recommended_escalation_reason: Optional[str]
    strategies_run: List[str]
    strategies_skipped: List[str]
    verification_timestamp: str
    model_id_verified: str


# ---------------------------------------------------------------------------
# REFLECTION MODULE TYPES
# ---------------------------------------------------------------------------

@dataclass
class RetryAttempt:
    """
    Immutable record of a single retry attempt within a reflection session.

    Attributes:
        attempt_number: 1-indexed attempt counter.
        model_id: Model used in this attempt.
        is_local: True if Ollama was used.
        action_taken: ReflectionAction that triggered this attempt.
        failure_category: Why the previous attempt failed.
        original_failure_reasons: Failure reasons from the previous verification.
        improved_prompt_applied: True if the prompt was modified before retry.
        prompt_improvement_type: Which improvement template was applied.
        response_received: The raw model response (or None on error).
        verification_score_after: Overall score from verification after this retry.
        success: True if verification passed after this attempt.
        latency_ms: Wall-clock latency for the model call in milliseconds.
        estimated_tokens_used: Estimated total tokens consumed in this attempt.
        timestamp: ISO-8601 UTC timestamp.
    """
    attempt_number: int
    model_id: str
    is_local: bool
    action_taken: ReflectionAction
    failure_category: FailureCategory
    original_failure_reasons: List[str]
    improved_prompt_applied: bool
    prompt_improvement_type: Optional[str]
    response_received: Optional[str]
    verification_score_after: Optional[float]
    success: bool
    latency_ms: float
    estimated_tokens_used: int
    timestamp: str = field(default_factory=_now_utc)


@dataclass
class ReflectionResult:
    """
    Final output of the Reflection Agent.

    Attributes:
        request_id: Correlation key.
        succeeded: True if a verified answer was produced.
        final_response: The accepted response text, or None on abort.
        final_model_id: Model that produced the accepted response.
        final_verification_result: Verification result of the final response.
        total_retries: Total retry attempts made.
        total_escalations: Number of tier escalations performed.
        retry_history: Ordered list of all RetryAttempt records.
        abort_reason: Why the agent aborted, if applicable.
        total_tokens_used: Total tokens across all attempts (local + remote).
        total_cost_usd: Total dollar cost across all Fireworks calls.
        total_latency_ms: Total wall-clock time in milliseconds.
        reflection_timestamp: ISO-8601 UTC timestamp.
    """
    request_id: str
    succeeded: bool
    final_response: Optional[str]
    final_model_id: str
    final_verification_result: Optional[VerificationResult]
    total_retries: int
    total_escalations: int
    retry_history: List[RetryAttempt]
    abort_reason: Optional[str]
    total_tokens_used: int
    total_cost_usd: float
    total_latency_ms: float
    reflection_timestamp: str = field(default_factory=_now_utc)
