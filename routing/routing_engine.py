"""
routing/routing_engine.py
==========================
Top-level Routing Engine — Module 3.5.

Orchestrates:
    ModelRegistry → UtilityScorer → EscalationPolicy → RoutingDecision

Routing algorithm:
    1. Check if LOCAL execution is viable (confidence ≥ threshold, no vision req).
       If yes, score the local model and return immediately if score is acceptable.
    2. Determine starting tier from EscalationPolicy (respects force_escalate_to).
    3. For each tier (ascending cost order):
         a. Get all models in that tier from the registry.
         b. Score them with UtilityScorer.
         c. Pick the top qualified candidate.
         d. If a viable candidate exists, build RoutingDecision and return.
    4. If all tiers exhausted, raise RuntimeError.

Local model always receives a configurable additive bonus before comparison,
ensuring it wins at equal quality — zero Fireworks tokens spent.
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import yaml

from core.interfaces import IRoutingEngine
from core.types import (
    CandidateScore,
    ExecutionTier,
    ModelProfile,
    RoutingContext,
    RoutingDecision,
)
from routing.escalation_policy import EscalationPolicy
from routing.model_registry import ModelRegistry
from routing.routing_telemetry import RoutingTelemetry
from routing.utility_scorer import UtilityScorer
from telemetry.telemetry_store import TelemetryStore

logger = logging.getLogger(__name__)


class RoutingEngine(IRoutingEngine):
    """
    Production Routing Engine.

    Selects the optimal model using progressive escalation and multi-dimensional
    utility scoring.  Always prefers local (Ollama) execution when viable.

    Args:
        models_json_path: Path to model_data/models.json.
        routing_config_path: Path to config/routing_config.yaml.
        telemetry_store: TelemetryStore instance for success-rate history.
        local_model_name: Name of the local Ollama model (from .env LOCAL_MODEL).
        ollama_url: URL of the Ollama API (from .env OLLAMA_URL).
    """

    _LOCAL_MODEL_ID = "local"

    def __init__(
        self,
        models_json_path: str,
        routing_config_path: str,
        telemetry_store: TelemetryStore,
        local_model_name: Optional[str] = None,
        ollama_url: Optional[str] = None,
    ) -> None:
        self._telemetry_store = telemetry_store
        self._routing_telemetry = RoutingTelemetry()

        # Load config
        with open(routing_config_path, "r", encoding="utf-8") as fh:
            self._cfg = yaml.safe_load(fh)
        self._local_cfg: Dict[str, Any] = self._cfg.get("local_execution", {})
        self._local_bonus: float = float(self._local_cfg.get("bonus", 0.35))
        self._local_min_conf: float = float(
            self._local_cfg.get("min_confidence_threshold", 0.60)
        )

        # Resolve local model settings from args or environment
        env_key_model = self._local_cfg.get("local_model_env_key", "LOCAL_MODEL")
        env_key_url = self._local_cfg.get("ollama_url_env_key", "OLLAMA_URL")
        self._local_model_name: str = (
            local_model_name
            or os.getenv(env_key_model, "llama3.1:8b")
        )
        self._ollama_url: str = (
            ollama_url
            or os.getenv(env_key_url, "http://localhost:11434/api/chat")
        )

        # Sub-components
        self._registry = ModelRegistry(models_json_path, routing_config_path)
        self._registry.load()

        self._scorer = UtilityScorer(routing_config_path)
        self._policy = EscalationPolicy(routing_config_path)

        # Build a synthetic ModelProfile for the local model
        self._local_profile: ModelProfile = self._build_local_profile()

    # ------------------------------------------------------------------
    # IRoutingEngine implementation
    # ------------------------------------------------------------------

    def route(self, context: RoutingContext) -> RoutingDecision:
        """
        Select the optimal model for the given RoutingContext.

        Always tries local execution first; escalates progressively only
        when local is not viable or does not meet quality requirements.

        Args:
            context: Full routing context.

        Returns:
            RoutingDecision with full diagnostics.

        Raises:
            RuntimeError: If no viable model is found across all tiers.
        """
        t_start = time.monotonic()
        history_scores = self._telemetry_store.get_all_success_rates()

        all_candidates: List[CandidateScore] = []
        escalation_attempt = 0

        # --- Step 1: Attempt local execution ---
        local_decision = self._try_local(context, history_scores, all_candidates)
        if local_decision is not None:
            latency_ms = (time.monotonic() - t_start) * 1000
            self._routing_telemetry.emit_escalation(
                context, "NONE", "LOCAL", "Local viable"
            )
            return self._finalise(local_decision, context, latency_ms)

        # --- Step 2: Progressive Fireworks escalation ---
        starting_tier = self._policy.get_starting_tier_order(context)
        current_tier = starting_tier

        while current_tier is not None:
            decision = self.route_for_tier(context, current_tier)
            if decision is not None:
                # Merge local candidates into all_candidates for full diagnostics
                decision = RoutingDecision(
                    request_id=decision.request_id,
                    selected_model_id=decision.selected_model_id,
                    selected_model_display_name=decision.selected_model_display_name,
                    selected_tier=decision.selected_tier,
                    is_local=decision.is_local,
                    utility_score=decision.utility_score,
                    score_breakdown=decision.score_breakdown,
                    all_candidates=all_candidates + decision.all_candidates,
                    escalation_tier_attempted=escalation_attempt,
                    estimated_cost_usd=decision.estimated_cost_usd,
                    api_parameters=decision.api_parameters,
                    routing_rationale=decision.routing_rationale,
                )
                latency_ms = (time.monotonic() - t_start) * 1000
                return self._finalise(decision, context, latency_ms)

            # Escalate
            next_tier = self._policy.get_next_tier_order(current_tier, context)
            if next_tier is not None:
                self._routing_telemetry.emit_escalation(
                    context,
                    self._policy.tier_order_to_label(current_tier),
                    self._policy.tier_order_to_label(next_tier),
                    "No viable model in tier",
                )
            current_tier = next_tier
            escalation_attempt += 1

        raise RuntimeError(
            f"[routing_engine] No viable model found for request {context.request_id}. "
            f"All tiers exhausted after {escalation_attempt} escalations."
        )

    def route_for_tier(
        self,
        context: RoutingContext,
        tier_order: int,
    ) -> Optional[RoutingDecision]:
        """
        Attempt routing restricted to a specific tier.

        Returns None if no model in that tier meets capability requirements.

        Args:
            context: Full routing context.
            tier_order: Numeric tier to search (0–4).
        """
        tier_label = self._policy.tier_order_to_label(tier_order)
        models_in_tier = self._registry.get_models_in_tier(tier_label)

        if not models_in_tier:
            logger.debug(
                "routing_tier_empty",
                extra={"tier": tier_label, "request_id": context.request_id},
            )
            return None

        history_scores = self._telemetry_store.get_all_success_rates()
        scored = self._scorer.score_all(models_in_tier, context, history_scores)

        # Pick the top qualified candidate
        top = next(
            (c for c in scored if c.meets_capability_requirements and c.utility_score > 0),
            None,
        )
        if top is None:
            return None

        profile = self._registry.get_profile(top.model_id)
        api_params = self._build_api_params(profile, context) if profile else {}
        tier_enum = self._tier_label_to_enum(tier_label)

        return RoutingDecision(
            request_id=context.request_id,
            selected_model_id=top.model_id,
            selected_model_display_name=top.display_name,
            selected_tier=tier_enum,
            is_local=False,
            utility_score=top.utility_score,
            score_breakdown=top.score_breakdown,
            all_candidates=scored,
            escalation_tier_attempted=tier_order,
            estimated_cost_usd=top.estimated_cost_usd,
            api_parameters=api_params,
            routing_rationale=(
                f"Selected {top.display_name} (tier={tier_label}) "
                f"with utility={top.utility_score:.3f}. "
                f"Est. cost: ${top.estimated_cost_usd:.6f}. "
                f"{profile.failure_modes or ''}"
            ),
        )

    # ------------------------------------------------------------------
    # LOCAL EXECUTION
    # ------------------------------------------------------------------

    def _try_local(
        self,
        context: RoutingContext,
        history_scores: Dict[str, float],
        all_candidates: List[CandidateScore],
    ) -> Optional[RoutingDecision]:
        """
        Evaluate local Ollama execution.  Returns a RoutingDecision if local
        is the best choice, None otherwise.
        """
        # Hard gate: local is not an option if vision is required or confidence too low
        if self._policy.should_skip_tier(0, context):
            logger.debug(
                "local_skipped",
                extra={
                    "request_id": context.request_id,
                    "local_confidence": context.confidence.local_confidence,
                    "requires_vision": context.complexity.requires_vision,
                },
            )
            return None

        # Score local model
        local_hist = history_scores.get(self._LOCAL_MODEL_ID, 0.75)
        local_candidate = self._scorer.score(self._local_profile, context, local_hist)

        # Apply local preference bonus
        boosted_utility = min(local_candidate.utility_score + self._local_bonus, 1.0)
        local_candidate = CandidateScore(
            model_id=local_candidate.model_id,
            display_name=local_candidate.display_name,
            routing_tier=local_candidate.routing_tier,
            tier_order=local_candidate.tier_order,
            utility_score=boosted_utility,
            score_breakdown=local_candidate.score_breakdown,
            weighted_breakdown=local_candidate.weighted_breakdown,
            is_local=True,
            estimated_cost_usd=0.0,
            meets_capability_requirements=local_candidate.meets_capability_requirements,
            disqualification_reasons=local_candidate.disqualification_reasons,
        )
        all_candidates.append(local_candidate)

        if not local_candidate.meets_capability_requirements:
            return None

        api_params = self._build_local_api_params(context)

        return RoutingDecision(
            request_id=context.request_id,
            selected_model_id=self._LOCAL_MODEL_ID,
            selected_model_display_name=f"Local ({self._local_model_name})",
            selected_tier=ExecutionTier.LOCAL,
            is_local=True,
            utility_score=boosted_utility,
            score_breakdown=local_candidate.score_breakdown,
            all_candidates=[local_candidate],
            escalation_tier_attempted=0,
            estimated_cost_usd=0.0,
            api_parameters=api_params,
            routing_rationale=(
                f"Local model ({self._local_model_name}) selected. "
                f"Utility (with bonus): {boosted_utility:.3f}. "
                f"Local confidence: {context.confidence.local_confidence:.3f}. "
                f"Zero Fireworks tokens consumed."
            ),
        )

    # ------------------------------------------------------------------
    # HELPERS
    # ------------------------------------------------------------------

    def _finalise(
        self,
        decision: RoutingDecision,
        context: RoutingContext,
        latency_ms: float,
    ) -> RoutingDecision:
        """Emit telemetry and return the final decision."""
        self._routing_telemetry.build_record(context, decision, latency_ms)
        logger.info(
            "routing_complete",
            extra={
                "request_id": context.request_id,
                "model": decision.selected_model_id,
                "tier": decision.selected_tier.value,
                "utility": round(decision.utility_score, 4),
                "latency_ms": round(latency_ms, 2),
            },
        )
        return decision

    def _build_api_params(
        self,
        profile: ModelProfile,
        context: RoutingContext,
    ) -> Dict[str, Any]:
        """
        Build a ready-to-use API parameters dict for a Fireworks model call.

        Respects the api_parameters capability flags from models.json.
        """
        params: Dict[str, Any] = {
            "model": profile.model_id,
            "messages": context.original_messages,
            "temperature": profile.preferred_temperature,
            "max_tokens": min(
                profile.preferred_max_tokens,
                profile.max_output_tokens,
            ),
        }
        # Conditionally add parameters only if the model supports them
        if profile.api_parameters.get("stream", False):
            params["stream"] = False  # Default to non-streaming for verifiability
        if profile.api_parameters.get("top_p", False):
            params["top_p"] = 0.95
        if (
            profile.api_parameters.get("response_format", False)
            and context.features.expected_output_format == "json"
        ):
            params["response_format"] = {"type": "json_object"}

        return params

    def _build_local_api_params(self, context: RoutingContext) -> Dict[str, Any]:
        """Build API params for an Ollama chat call."""
        return {
            "model": self._local_model_name,
            "messages": context.original_messages,
            "stream": False,
            "options": {
                "temperature": 0.7,
                "num_predict": 2048,
            },
        }

    def _build_local_profile(self) -> ModelProfile:
        """
        Synthesize a ModelProfile for the local Ollama model.

        Uses conservative mid-range scores so local is always preferred when
        the task is within its capability but not preferred for highly complex
        tasks where Fireworks models score much higher.
        """
        return ModelProfile(
            model_id=self._LOCAL_MODEL_ID,
            display_name=f"Local ({self._local_model_name})",
            provider="Ollama",
            routing_tier="Local",
            tier_order=0,
            quality_score=0.60,
            reasoning_score=0.55,
            coding_score=0.55,
            vision_score=None,
            token_efficiency_score=1.0,  # Zero cost = maximum efficiency
            cost_score=1.0,              # Free
            latency_score=0.70,          # Fast but not as fast as cloud GPU
            recommended_confidence_threshold=self._local_min_conf,
            recommended_task_complexity="Simple",
            input_cost_per_million=0.0,
            output_cost_per_million=0.0,
            has_vision=False,
            context_window=8192,
            max_output_tokens=2048,
            preferred_temperature=0.7,
            preferred_max_tokens=2048,
            preferred_prompt_style="Clear and concise instructions.",
            agent_recommendations={},
            api_parameters={"stream": True},
            failure_modes="May struggle with complex reasoning or vision tasks.",
            prompt_engineering_tips="Keep prompts short and explicit.",
            latency_class="Fast",
        )

    @staticmethod
    def _tier_label_to_enum(label: str) -> ExecutionTier:
        """Map a routing_tier label string to the ExecutionTier enum."""
        mapping = {
            "Local": ExecutionTier.LOCAL,
            "Cheap": ExecutionTier.CHEAP,
            "Balanced": ExecutionTier.BALANCED,
            "Premium": ExecutionTier.PREMIUM,
            "Ultra Premium": ExecutionTier.ULTRA_PREMIUM,
        }
        return mapping.get(label, ExecutionTier.BALANCED)
