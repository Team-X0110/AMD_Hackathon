"""
core/interfaces.py
==================
Abstract base class contracts for every major component.

All concrete implementations must subclass the appropriate interface here.
This enforces the Dependency Inversion Principle: high-level orchestrators
depend only on these abstractions, never on concrete implementations.

Import order:
    Only imports from core.types — no other project modules.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from core.types import (
    CandidateScore,
    FailureCategory,
    ModelProfile,
    ReflectionAction,
    ReflectionResult,
    RetryAttempt,
    RoutingContext,
    RoutingDecision,
    StrategyResult,
    VerificationResult,
)


# ---------------------------------------------------------------------------
# ROUTING ENGINE INTERFACES
# ---------------------------------------------------------------------------

class IModelRegistry(ABC):
    """
    Contract for loading and querying the model catalogue.

    Implementations load models.json and expose typed ModelProfile objects.
    The registry must be hot-reloadable: calling load() again refreshes state.
    """

    @abstractmethod
    def load(self) -> None:
        """
        (Re-)load the model catalogue from the backing store (models.json).

        Raises:
            FileNotFoundError: If models.json cannot be found.
            ValueError: If models.json is malformed.
        """

    @abstractmethod
    def get_all_profiles(self) -> List[ModelProfile]:
        """Return all loaded ModelProfile objects (Fireworks models only)."""

    @abstractmethod
    def get_profile(self, model_id: str) -> Optional[ModelProfile]:
        """
        Return the ModelProfile for a given model_id, or None if not found.

        Args:
            model_id: Full Fireworks model ID string.
        """

    @abstractmethod
    def get_models_in_tier(self, tier_label: str) -> List[ModelProfile]:
        """
        Return all models whose routing_tier matches tier_label.

        Args:
            tier_label: Tier label string as defined in routing_config.yaml.
        """

    @abstractmethod
    def get_best_coding_model(self, min_coding_score: float) -> Optional[ModelProfile]:
        """
        Return the model with the highest coding_score that meets the minimum.

        Args:
            min_coding_score: Minimum normalised coding score [0.0, 1.0].
        """


class IUtilityScorer(ABC):
    """
    Contract for computing multi-dimensional utility scores.

    Implementations must be stateless: the same inputs always produce the
    same outputs.  Historical performance data is injected via the registry.
    """

    @abstractmethod
    def score(
        self,
        model: ModelProfile,
        context: RoutingContext,
        history_score: float,
    ) -> CandidateScore:
        """
        Compute the utility score for a single model given the routing context.

        Args:
            model: The candidate model profile.
            context: Full routing context including features, complexity, confidence.
            history_score: Rolling success rate for this model [0.0, 1.0].

        Returns:
            CandidateScore with full breakdown.
        """

    @abstractmethod
    def score_all(
        self,
        models: List[ModelProfile],
        context: RoutingContext,
        history_scores: Dict[str, float],
    ) -> List[CandidateScore]:
        """
        Score all candidate models and return them sorted by utility_score DESC.

        Args:
            models: List of candidate model profiles.
            context: Full routing context.
            history_scores: Dict of model_id → rolling success rate.

        Returns:
            List of CandidateScore objects, best first.
        """


class IEscalationPolicy(ABC):
    """
    Contract for determining the progressive tier escalation order.

    The policy decides which tier to attempt first, which to skip,
    and which tier to move to after a failure.
    """

    @abstractmethod
    def get_starting_tier_order(self, context: RoutingContext) -> int:
        """
        Return the tier order (0–4) to attempt first for this context.

        Respects force_escalate_to and skip rules from routing_config.yaml.

        Args:
            context: Full routing context.

        Returns:
            Integer tier order number.
        """

    @abstractmethod
    def get_next_tier_order(
        self,
        current_tier_order: int,
        context: RoutingContext,
    ) -> Optional[int]:
        """
        Return the next tier order to attempt after current_tier_order fails.

        Returns None if no higher tier is available (escalation exhausted).

        Args:
            current_tier_order: The tier that just failed.
            context: Full routing context.
        """

    @abstractmethod
    def should_skip_tier(self, tier_order: int, context: RoutingContext) -> bool:
        """
        Return True if the given tier should be skipped for this context.

        Args:
            tier_order: Tier to evaluate.
            context: Full routing context.
        """

    @abstractmethod
    def tier_order_to_label(self, tier_order: int) -> str:
        """Convert a numeric tier order to its string label."""

    @abstractmethod
    def tier_label_to_order(self, tier_label: str) -> int:
        """Convert a tier label string to its numeric order."""


class IRoutingEngine(ABC):
    """
    Top-level contract for the Routing Engine.

    The engine selects the best model for a given RoutingContext, applying
    progressive escalation, utility scoring, and local preference.
    """

    @abstractmethod
    def route(self, context: RoutingContext) -> RoutingDecision:
        """
        Select the optimal model for the given routing context.

        Starts at the lowest viable tier and escalates only if needed.
        Always prefers local execution when the confidence threshold is met.

        Args:
            context: Full routing context.

        Returns:
            RoutingDecision with the selected model and full diagnostics.

        Raises:
            RuntimeError: If no viable model can be found across all tiers.
        """

    @abstractmethod
    def route_for_tier(
        self,
        context: RoutingContext,
        tier_order: int,
    ) -> Optional[RoutingDecision]:
        """
        Attempt routing restricted to a specific tier.

        Returns None if no model in that tier is viable.

        Args:
            context: Full routing context.
            tier_order: The tier to search within.
        """


# ---------------------------------------------------------------------------
# VERIFICATION INTERFACES
# ---------------------------------------------------------------------------

class IVerificationStrategy(ABC):
    """
    Contract for a single pluggable verification strategy.

    Each strategy is independently configurable via verifier_config.yaml.
    Strategies must not make Fireworks API calls — verification is local.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique strategy name.  Must match the key in verifier_config.yaml."""

    @abstractmethod
    def should_run(
        self,
        context: RoutingContext,
        response: str,
        model_id: str,
    ) -> bool:
        """
        Return True if this strategy should execute for the given context.

        Use this to implement cost-aware skipping (e.g. skip self-consistency
        for low-risk tasks).

        Args:
            context: Full routing context.
            response: The model's raw response string.
            model_id: ID of the model that produced the response.
        """

    @abstractmethod
    def verify(
        self,
        context: RoutingContext,
        response: str,
        model_id: str,
    ) -> StrategyResult:
        """
        Execute the verification check and return a structured result.

        Implementations must never raise unhandled exceptions — capture errors
        and encode them as failure_reasons in the returned StrategyResult.

        Args:
            context: Full routing context (includes prompt, features, complexity).
            response: The model's raw response string.
            model_id: ID of the model that produced the response.

        Returns:
            StrategyResult with full diagnostics.
        """


class IVerifier(ABC):
    """
    Top-level contract for the Local Verifier orchestrator.

    Runs all applicable strategies and aggregates results into a single
    VerificationResult without making any Fireworks API calls.
    """

    @abstractmethod
    def verify(
        self,
        context: RoutingContext,
        response: str,
        model_id: str,
    ) -> VerificationResult:
        """
        Run all applicable verification strategies and return aggregated result.

        Args:
            context: Full routing context.
            response: Model response to verify.
            model_id: ID of the model that produced the response.

        Returns:
            VerificationResult with full diagnostics and escalation recommendation.
        """


# ---------------------------------------------------------------------------
# REFLECTION INTERFACES
# ---------------------------------------------------------------------------

class IFailureClassifier(ABC):
    """Contract for classifying WHY verification failed."""

    @abstractmethod
    def classify(
        self,
        verification_result: VerificationResult,
        context: RoutingContext,
        response: str,
    ) -> FailureCategory:
        """
        Determine the primary failure category from a failed VerificationResult.

        Args:
            verification_result: The failed verification.
            context: Full routing context.
            response: The model response that failed verification.

        Returns:
            The most specific FailureCategory that applies.
        """


class IPromptImprover(ABC):
    """Contract for rewriting prompts before a retry attempt."""

    @abstractmethod
    def improve(
        self,
        context: RoutingContext,
        action: ReflectionAction,
        attempt_number: int,
        failure_reasons: List[str],
    ) -> RoutingContext:
        """
        Return a new RoutingContext with an improved prompt for retry.

        The original RoutingContext is never mutated.

        Args:
            context: The original routing context.
            action: The reflection action that triggered this improvement.
            attempt_number: Current retry count (1-indexed).
            failure_reasons: List of failure reasons from the last verification.

        Returns:
            New RoutingContext with improved original_messages and/or
            additional_context.
        """


class IRetryHistory(ABC):
    """Contract for the immutable retry attempt log."""

    @abstractmethod
    def record(self, attempt: RetryAttempt) -> None:
        """Append a RetryAttempt to the history."""

    @abstractmethod
    def get_all(self) -> List[RetryAttempt]:
        """Return all recorded attempts in chronological order."""

    @abstractmethod
    def get_total_retries(self) -> int:
        """Return total number of attempts recorded."""

    @abstractmethod
    def get_total_tokens(self) -> int:
        """Return sum of estimated_tokens_used across all attempts."""

    @abstractmethod
    def get_total_cost(self) -> float:
        """Return estimated total cost in USD across all Fireworks attempts."""

    @abstractmethod
    def get_total_latency_ms(self) -> float:
        """Return sum of latency_ms across all attempts."""


class IActionResolver(ABC):
    """Contract for mapping a FailureCategory to a ReflectionAction."""

    @abstractmethod
    def resolve(
        self,
        failure_category: FailureCategory,
        attempt_number: int,
        is_currently_local: bool,
    ) -> ReflectionAction:
        """
        Determine what action to take given a failure category and retry state.

        Automatically falls back to the fallback_action when
        max_retries_before_fallback is exceeded.

        Args:
            failure_category: Classified reason for failure.
            attempt_number: Current attempt count (used to decide primary vs fallback).
            is_currently_local: True if the last attempt was on Ollama.

        Returns:
            The ReflectionAction to execute next.
        """


class IReflectionAgent(ABC):
    """
    Top-level contract for the Reflection Agent orchestrator.

    The agent coordinates failure classification, prompt improvement,
    action resolution, and retry/escalation in a controlled loop.
    """

    @abstractmethod
    def reflect(
        self,
        context: RoutingContext,
        initial_response: str,
        initial_verification: VerificationResult,
        initial_routing_decision: RoutingDecision,
    ) -> ReflectionResult:
        """
        Run the reflection loop until success, abort, or retry budget exhaustion.

        Args:
            context: Full routing context (original, unmodified).
            initial_response: The response that failed initial verification.
            initial_verification: The VerificationResult that triggered reflection.
            initial_routing_decision: The RoutingDecision that produced the response.

        Returns:
            ReflectionResult with the final accepted response or abort reason.
        """
