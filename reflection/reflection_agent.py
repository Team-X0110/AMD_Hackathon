"""
reflection/reflection_agent.py
================================
Reflection Agent orchestrator — Module 3.7.

Coordinates the full retry loop:
    FailureClassifier → ActionResolver → PromptImprover
    → RoutingEngine (escalate/switch) → Verifier → repeat

Retry budget enforcement:
    - max_local_retries   from reflection_config.yaml
    - max_fireworks_retries
    - max_total_retries   (hard ceiling)
    - Loop detection via RetryHistory.has_infinite_loop()

Priority: local retries first, then Fireworks — token-minimization first.

Abort conditions:
    - UNSAFE_OUTPUT detected
    - ABORT action resolved
    - All retry budgets exhausted
    - Escalation exhausted (no higher tier available)
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

import yaml

from core.interfaces import IReflectionAgent
from core.types import (
    FailureCategory,
    ReflectionAction,
    ReflectionResult,
    RetryAttempt,
    RoutingContext,
    RoutingDecision,
    VerificationResult,
    VerificationStatus,
)
from reflection.action_resolver import ActionResolver
from reflection.failure_classifier import FailureClassifier
from reflection.prompt_improver import PromptImprover
from reflection.retry_history import RetryHistory

logger = logging.getLogger(__name__)

# Type alias for the inference callable injected from outside
InferenceCallable = Callable[[str, Dict[str, Any], bool], str]
# Signature: (model_id, api_params, is_local) -> response_text

RouteCallable = Callable[[RoutingContext, int], Optional[RoutingDecision]]
# Signature: (context, min_tier_order) -> RoutingDecision or None

VerifyCallable = Callable[[RoutingContext, str, str], VerificationResult]
# Signature: (context, response, model_id) -> VerificationResult


def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


class ReflectionAgent(IReflectionAgent):
    """
    Production Reflection Agent.

    Determines WHY verification failed, improves the prompt, selects the
    appropriate retry strategy, and loops until success or budget exhaustion.

    Args:
        reflection_config_path: Path to config/reflection_config.yaml.
        routing_config_path: Path to config/routing_config.yaml.
        inference_fn: Callable(model_id, api_params, is_local) -> response_str.
            Handles both Ollama (is_local=True) and Fireworks calls.
        route_fn: Callable(context, min_tier_order) -> RoutingDecision or None.
            Used to re-route when escalation is needed.  Typically wraps
            RoutingEngine.route_for_tier().
        verify_fn: Callable(context, response, model_id) -> VerificationResult.
            Used to verify each retry response.
        confidence_threshold: Minimum verification confidence before escalation.
    """

    def __init__(
        self,
        reflection_config_path: str,
        routing_config_path: str,
        inference_fn: InferenceCallable,
        route_fn: RouteCallable,
        verify_fn: VerifyCallable,
        confidence_threshold: float = 0.55,
    ) -> None:
        with open(reflection_config_path, "r", encoding="utf-8") as fh:
            self._cfg = yaml.safe_load(fh)

        retry_policy = self._cfg.get("retry_policy", {})
        self._max_total_retries: int = int(retry_policy.get("max_total_retries", 4))
        self._max_local_retries: int = int(retry_policy.get("max_local_retries", 2))
        self._max_fireworks_retries: int = int(
            retry_policy.get("max_fireworks_retries", 2)
        )
        self._backoff_initial: float = float(
            retry_policy.get("retry_backoff_seconds", 0.5)
        )
        self._backoff_multiplier: float = float(
            retry_policy.get("backoff_multiplier", 2.0)
        )
        self._max_backoff: float = float(
            retry_policy.get("max_backoff_seconds", 8.0)
        )
        self._coding_min_score: float = float(
            self._cfg.get("coding_specialist_min_coding_score", 90) / 100.0
        )

        self._inference_fn = inference_fn
        self._route_fn = route_fn
        self._verify_fn = verify_fn

        self._classifier = FailureClassifier(
            confidence_threshold=confidence_threshold
        )
        self._improver = PromptImprover(reflection_config_path)
        self._resolver = ActionResolver(reflection_config_path)

    # ------------------------------------------------------------------
    # IReflectionAgent implementation
    # ------------------------------------------------------------------

    def reflect(
        self,
        context: RoutingContext,
        initial_response: str,
        initial_verification: VerificationResult,
        initial_routing_decision: RoutingDecision,
    ) -> ReflectionResult:
        """
        Run the reflection loop until success, abort, or budget exhaustion.

        Args:
            context: Full routing context (original, unmodified).
            initial_response: The response that failed initial verification.
            initial_verification: The VerificationResult that triggered reflection.
            initial_routing_decision: The RoutingDecision that produced the response.

        Returns:
            ReflectionResult with the final accepted response or abort reason.
        """
        t_start = time.monotonic()
        history = RetryHistory()

        current_context = context
        current_model_id = initial_routing_decision.selected_model_id
        current_is_local = initial_routing_decision.is_local
        current_tier_order = initial_routing_decision.escalation_tier_attempted
        current_api_params = initial_routing_decision.api_parameters
        current_verification = initial_verification

        local_retries_used = 0
        fireworks_retries_used = 0
        attempt_number = 0
        abort_reason: Optional[str] = None

        logger.info(
            "reflection_started",
            extra={
                "request_id": context.request_id,
                "initial_model": current_model_id,
                "initial_tier": initial_routing_decision.selected_tier.value,
                "initial_score": initial_verification.overall_score,
            },
        )

        while True:
            attempt_number += 1

            # --- Budget checks ---
            if attempt_number > self._max_total_retries:
                abort_reason = (
                    f"Maximum total retries ({self._max_total_retries}) exhausted"
                )
                break

            # --- Classify failure ---
            failure_category = self._classifier.classify(
                current_verification, current_context, initial_response
            )

            # --- Abort immediately on unsafe content ---
            if failure_category == FailureCategory.UNSAFE_OUTPUT:
                abort_reason = "UNSAFE_OUTPUT detected — aborting immediately"
                logger.warning(
                    "reflection_abort_unsafe",
                    extra={"request_id": context.request_id},
                )
                break

            # --- Resolve action ---
            action = self._resolver.resolve(
                failure_category=failure_category,
                attempt_number=attempt_number,
                is_currently_local=current_is_local,
            )

            if action == ReflectionAction.ABORT:
                abort_reason = (
                    f"ABORT action resolved for category {failure_category.value}"
                )
                break

            # --- Infinite loop guard ---
            if history.has_infinite_loop(current_model_id, action, max_repeat=2):
                logger.warning(
                    "reflection_loop_detected",
                    extra={
                        "model_id": current_model_id,
                        "action": action.value,
                        "request_id": context.request_id,
                    },
                )
                # Force escalation to break the loop
                action = ReflectionAction.ESCALATE

            # --- Determine next model + context ---
            next_model_id, next_is_local, next_tier_order, next_api_params, \
                next_context, should_abort = self._prepare_next_attempt(
                    action=action,
                    current_context=current_context,
                    current_model_id=current_model_id,
                    current_is_local=current_is_local,
                    current_tier_order=current_tier_order,
                    current_api_params=current_api_params,
                    attempt_number=attempt_number,
                    failure_category=failure_category,
                    failure_reasons=current_verification.failure_reasons,
                    local_retries_used=local_retries_used,
                    fireworks_retries_used=fireworks_retries_used,
                )

            if should_abort:
                abort_reason = "Escalation exhausted — no viable model found"
                break

            # --- Check per-tier retry budgets ---
            if next_is_local and local_retries_used >= self._max_local_retries:
                # Force escalate
                logger.info(
                    "reflection_local_budget_exhausted",
                    extra={"request_id": context.request_id},
                )
                action = ReflectionAction.ESCALATE
                next_model_id, next_is_local, next_tier_order, next_api_params, \
                    next_context, should_abort = self._prepare_next_attempt(
                        action=action,
                        current_context=current_context,
                        current_model_id=current_model_id,
                        current_is_local=False,  # Force non-local
                        current_tier_order=current_tier_order,
                        current_api_params=current_api_params,
                        attempt_number=attempt_number,
                        failure_category=failure_category,
                        failure_reasons=current_verification.failure_reasons,
                        local_retries_used=local_retries_used,
                        fireworks_retries_used=fireworks_retries_used,
                    )
                if should_abort:
                    abort_reason = "Local budget exhausted and escalation failed"
                    break

            if not next_is_local and fireworks_retries_used >= self._max_fireworks_retries:
                abort_reason = (
                    f"Fireworks retry budget ({self._max_fireworks_retries}) exhausted"
                )
                break

            # --- Execute the retry ---
            backoff = min(
                self._backoff_initial * (self._backoff_multiplier ** (attempt_number - 1)),
                self._max_backoff,
            )
            if backoff > 0 and attempt_number > 1:
                time.sleep(backoff)

            t_attempt = time.monotonic()
            retry_response: Optional[str] = None
            attempt_error: Optional[str] = None

            try:
                retry_response = self._inference_fn(
                    next_model_id, next_api_params, next_is_local
                )
            except Exception as exc:
                attempt_error = str(exc)
                logger.error(
                    "reflection_inference_failed",
                    extra={
                        "attempt": attempt_number,
                        "model_id": next_model_id,
                        "error": str(exc),
                        "request_id": context.request_id,
                    },
                    exc_info=True,
                )

            attempt_latency = (time.monotonic() - t_attempt) * 1000

            if next_is_local:
                local_retries_used += 1
            else:
                fireworks_retries_used += 1

            # --- Verify retry response ---
            retry_verification: Optional[VerificationResult] = None
            if retry_response:
                retry_verification = self._verify_fn(
                    next_context, retry_response, next_model_id
                )

            success = (
                retry_verification is not None
                and retry_verification.status == VerificationStatus.PASSED
            )

            # --- Record attempt ---
            token_estimate = self._estimate_tokens(
                next_context, retry_response or ""
            )
            attempt = RetryAttempt(
                attempt_number=attempt_number,
                model_id=next_model_id,
                is_local=next_is_local,
                action_taken=action,
                failure_category=failure_category,
                original_failure_reasons=current_verification.failure_reasons,
                improved_prompt_applied=bool(
                    next_context.metadata.get("improvement_applied")
                ),
                prompt_improvement_type=next_context.metadata.get("improvement_type"),
                response_received=retry_response,
                verification_score_after=(
                    retry_verification.overall_score if retry_verification else None
                ),
                success=success,
                latency_ms=attempt_latency,
                estimated_tokens_used=token_estimate,
            )
            history.record(attempt)

            logger.info(
                "reflection_attempt_complete",
                extra={
                    "attempt": attempt_number,
                    "model_id": next_model_id,
                    "action": action.value,
                    "success": success,
                    "score": round(retry_verification.overall_score, 4) if retry_verification else None,
                    "latency_ms": round(attempt_latency, 2),
                    "request_id": context.request_id,
                },
            )

            if success:
                # Verification passed — return the accepted response
                total_latency = (time.monotonic() - t_start) * 1000
                summary = history.summarise()
                logger.info(
                    "reflection_succeeded",
                    extra={
                        "request_id": context.request_id,
                        "total_retries": attempt_number,
                        "final_model": next_model_id,
                        "total_latency_ms": round(total_latency, 2),
                    },
                )
                return ReflectionResult(
                    request_id=context.request_id,
                    succeeded=True,
                    final_response=retry_response,
                    final_model_id=next_model_id,
                    final_verification_result=retry_verification,
                    total_retries=attempt_number,
                    total_escalations=history.get_escalation_count(),
                    retry_history=history.get_all(),
                    abort_reason=None,
                    total_tokens_used=summary["total_tokens_used"],
                    total_cost_usd=summary["total_cost_usd"],
                    total_latency_ms=total_latency,
                )

            # Update state for next iteration
            current_context = next_context
            current_model_id = next_model_id
            current_is_local = next_is_local
            current_tier_order = next_tier_order
            current_api_params = next_api_params
            current_verification = retry_verification or current_verification

        # ---- Exhausted / aborted ----
        total_latency = (time.monotonic() - t_start) * 1000
        summary = history.summarise()

        logger.warning(
            "reflection_failed",
            extra={
                "request_id": context.request_id,
                "abort_reason": abort_reason,
                "total_retries": attempt_number,
                "total_latency_ms": round(total_latency, 2),
            },
        )

        return ReflectionResult(
            request_id=context.request_id,
            succeeded=False,
            final_response=None,
            final_model_id=current_model_id,
            final_verification_result=current_verification,
            total_retries=attempt_number,
            total_escalations=history.get_escalation_count(),
            retry_history=history.get_all(),
            abort_reason=abort_reason,
            total_tokens_used=summary["total_tokens_used"],
            total_cost_usd=summary["total_cost_usd"],
            total_latency_ms=total_latency,
        )

    # ------------------------------------------------------------------
    # PRIVATE HELPERS
    # ------------------------------------------------------------------

    def _prepare_next_attempt(
        self,
        action: ReflectionAction,
        current_context: RoutingContext,
        current_model_id: str,
        current_is_local: bool,
        current_tier_order: int,
        current_api_params: Dict[str, Any],
        attempt_number: int,
        failure_category: FailureCategory,
        failure_reasons: List[str],
        local_retries_used: int,
        fireworks_retries_used: int,
    ):
        """
        Determine the model, context, and parameters for the next attempt.

        Returns:
            (next_model_id, next_is_local, next_tier_order, next_api_params,
             next_context, should_abort)
        """
        next_context = self._improver.improve(
            context=current_context,
            action=action,
            attempt_number=attempt_number,
            failure_reasons=failure_reasons,
        )

        # Actions that keep the same model
        same_model_actions = {
            ReflectionAction.RETRY_SAME_COT,
            ReflectionAction.RETRY_SAME_GROUNDING,
            ReflectionAction.RETRY_SAME_FORMAT,
            ReflectionAction.RETRY_SAME_SCHEMA,
            ReflectionAction.RETRY_WITH_CONTEXT,
            ReflectionAction.RETRY_TOOL_SIMPLIFY,
        }

        if action in same_model_actions:
            return (
                current_model_id,
                current_is_local,
                current_tier_order,
                current_api_params,
                next_context,
                False,
            )

        # ESCALATE / ESCALATE_AFTER_RETRY / RETRY_CODING_MODEL → get new model
        if action in (
            ReflectionAction.ESCALATE,
            ReflectionAction.ESCALATE_AFTER_RETRY,
            ReflectionAction.RETRY_CODING_MODEL,
        ):
            # Target tier: one above current
            target_tier = current_tier_order + 1 if not current_is_local else 1
            new_decision = self._route_fn(next_context, target_tier)

            if new_decision is None:
                return (
                    current_model_id,
                    current_is_local,
                    current_tier_order,
                    current_api_params,
                    next_context,
                    True,  # should_abort
                )

            logger.info(
                "reflection_escalated",
                extra={
                    "request_id": current_context.request_id,
                    "from_model": current_model_id,
                    "to_model": new_decision.selected_model_id,
                    "from_tier": current_tier_order,
                    "to_tier": new_decision.escalation_tier_attempted,
                    "action": action.value,
                },
            )
            return (
                new_decision.selected_model_id,
                new_decision.is_local,
                new_decision.escalation_tier_attempted,
                new_decision.api_parameters,
                next_context,
                False,
            )

        # Fallback
        return (
            current_model_id,
            current_is_local,
            current_tier_order,
            current_api_params,
            next_context,
            False,
        )

    @staticmethod
    def _estimate_tokens(context: RoutingContext, response: str) -> int:
        """
        Estimate total tokens used in one attempt (prompt + response).
        Uses the 1 token ≈ 4 chars heuristic.
        """
        prompt_chars = sum(
            len(str(m.get("content", "")))
            for m in context.original_messages
        )
        response_chars = len(response)
        return (prompt_chars + response_chars) // 4
