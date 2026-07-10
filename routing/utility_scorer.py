"""
routing/utility_scorer.py
==========================
Multi-dimensional weighted utility scorer for model candidate selection.

The utility score formula:
    U(model, context) = Σ wᵢ · fᵢ(model, context)

where all fᵢ ∈ [0.0, 1.0] and Σ wᵢ = 1.0.

Components:
    quality_score     — overall model quality from routing_metadata
    domain_match      — task-specific recommendation score
    reasoning_score   — weighted by whether reasoning is needed
    coding_score      — weighted by whether coding is needed
    vision_score      — weighted by whether vision is needed (0 if no vision)
    token_efficiency  — favours token-efficient models
    latency_score     — favours faster models
    cost_penalty      — 1 - normalised_cost (cheaper = higher score)
    confidence_match  — 1 - |task_confidence - model_threshold|
    history_factor    — rolling success rate from telemetry

Local models receive an additional additive bonus (see routing_config.yaml).
"""

from __future__ import annotations

import logging
import math
from typing import Any, Dict, List, Optional

import yaml

from core.interfaces import IUtilityScorer
from core.types import CandidateScore, ModelProfile, RoutingContext, TaskType

logger = logging.getLogger(__name__)


class UtilityScorer(IUtilityScorer):
    """
    Weighted utility scorer.  All weights are loaded from routing_config.yaml.

    Args:
        routing_config_path: Path to routing_config.yaml.
    """

    def __init__(self, routing_config_path: str) -> None:
        self._cfg = self._load_config(routing_config_path)
        self._weights: Dict[str, float] = self._cfg["utility_weights"]
        self._cost_cfg: Dict[str, float] = self._cfg["cost_normalization"]
        self._task_key_map: Dict[str, str] = self._cfg.get(
            "task_type_to_recommendation_key", {}
        )
        self._min_utility: float = self._cfg.get("candidate_selection", {}).get(
            "min_utility_threshold", 0.10
        )
        # Validate weights sum ≈ 1.0
        total = sum(self._weights.values())
        if not math.isclose(total, 1.0, abs_tol=0.02):
            logger.warning(
                "utility_weights_do_not_sum_to_1",
                extra={"sum": total},
            )

    # ------------------------------------------------------------------
    # IUtilityScorer implementation
    # ------------------------------------------------------------------

    def score(
        self,
        model: ModelProfile,
        context: RoutingContext,
        history_score: float,
    ) -> CandidateScore:
        """
        Compute a CandidateScore for one model.

        Args:
            model: The candidate model profile.
            context: Full routing context.
            history_score: Rolling success rate for this model [0.0, 1.0].

        Returns:
            CandidateScore with full breakdown.
        """
        disqualification_reasons: List[str] = []
        meets_requirements = True

        # --- Capability gating (hard disqualifications) ---
        if context.complexity.requires_vision and not model.has_vision:
            disqualification_reasons.append(
                "Model lacks vision capability required by task"
            )
            meets_requirements = False

        # --- Raw component scores ---
        breakdown: Dict[str, float] = {}

        breakdown["quality_score"] = model.quality_score

        breakdown["domain_match"] = self._compute_domain_match(model, context)

        # Reasoning: only contribute full weight when task needs reasoning
        if context.complexity.requires_reasoning:
            breakdown["reasoning_score"] = model.reasoning_score
        else:
            breakdown["reasoning_score"] = model.reasoning_score * 0.5

        # Coding: only contribute full weight when task needs coding
        if context.complexity.requires_coding:
            breakdown["coding_score"] = model.coding_score
        else:
            breakdown["coding_score"] = model.coding_score * 0.5

        # Vision: only matters when task needs vision
        if context.complexity.requires_vision:
            breakdown["vision_score"] = model.vision_score if model.vision_score is not None else 0.0
        else:
            breakdown["vision_score"] = 0.5  # Neutral when not needed

        breakdown["token_efficiency"] = model.token_efficiency_score

        breakdown["latency_score"] = model.latency_score

        breakdown["cost_penalty"] = self._compute_cost_penalty(model, context)

        breakdown["confidence_match"] = self._compute_confidence_match(model, context)

        breakdown["history_factor"] = history_score

        # --- Weighted sum ---
        weighted: Dict[str, float] = {}
        utility = 0.0
        for component, raw_score in breakdown.items():
            weight = self._weights.get(component, 0.0)
            contribution = weight * raw_score
            weighted[component] = contribution
            utility += contribution

        # Clamp to [0, 1]
        utility = max(0.0, min(utility, 1.0))

        # Estimated cost for this specific request
        est_cost = self._estimate_request_cost(model, context)

        return CandidateScore(
            model_id=model.model_id,
            display_name=model.display_name,
            routing_tier=model.routing_tier,
            tier_order=model.tier_order,
            utility_score=utility,
            score_breakdown=breakdown,
            weighted_breakdown=weighted,
            is_local=False,
            estimated_cost_usd=est_cost,
            meets_capability_requirements=meets_requirements,
            disqualification_reasons=disqualification_reasons,
        )

    def score_all(
        self,
        models: List[ModelProfile],
        context: RoutingContext,
        history_scores: Dict[str, float],
    ) -> List[CandidateScore]:
        """
        Score all candidates and return them sorted by utility_score DESC.

        Models that fail hard capability checks are included at the bottom
        of the list with utility_score = 0 and meets_capability_requirements = False.
        """
        scored: List[CandidateScore] = []
        for model in models:
            h = history_scores.get(model.model_id, 0.75)
            candidate = self.score(model, context, h)
            scored.append(candidate)

        # Sort: qualified first (utility DESC), disqualified last
        scored.sort(
            key=lambda c: (
                c.meets_capability_requirements,
                c.utility_score,
            ),
            reverse=True,
        )
        return scored

    # ------------------------------------------------------------------
    # PRIVATE HELPERS
    # ------------------------------------------------------------------

    def _compute_domain_match(
        self,
        model: ModelProfile,
        context: RoutingContext,
    ) -> float:
        """
        Map the primary_task_type to the corresponding agent_recommendations key
        and return the normalised score.
        """
        task_str = context.features.primary_task_type.value
        rec_key = self._task_key_map.get(task_str)
        if not rec_key:
            return 0.5  # Neutral when mapping is unknown

        score = model.agent_recommendations.get(rec_key)
        if score is None:
            # Model doesn't support this task type
            return 0.0
        return float(score)  # Already normalised by ModelRegistry

    def _compute_cost_penalty(
        self,
        model: ModelProfile,
        context: RoutingContext,
    ) -> float:
        """
        Return a cost attractiveness score in [0, 1] — higher = cheaper.

        Uses estimated_output_tokens to weight output cost more heavily
        than input cost (realistic for generation-heavy workloads).
        """
        input_ceil = float(self._cost_cfg.get("max_input_cost_per_million", 2.0))
        output_ceil = float(self._cost_cfg.get("max_output_cost_per_million", 5.0))
        in_w = float(self._cost_cfg.get("input_weight", 0.4))
        out_w = float(self._cost_cfg.get("output_weight", 0.6))

        norm_in = 1.0 - min(model.input_cost_per_million / input_ceil, 1.0)
        norm_out = 1.0 - min(model.output_cost_per_million / output_ceil, 1.0)
        return in_w * norm_in + out_w * norm_out

    def _compute_confidence_match(
        self,
        model: ModelProfile,
        context: RoutingContext,
    ) -> float:
        """
        Reward models whose recommended_confidence_threshold closely matches
        the task's overall_confidence.

        A perfect match returns 1.0; a delta of ≥ 1.0 returns 0.0.
        """
        delta = abs(
            context.confidence.overall_confidence
            - model.recommended_confidence_threshold
        )
        return max(0.0, 1.0 - delta)

    def _estimate_request_cost(
        self,
        model: ModelProfile,
        context: RoutingContext,
    ) -> float:
        """
        Estimate the dollar cost for one API call with this model.

        Estimation = (prompt_tokens / 1M * input_cost)
                   + (estimated_output_tokens / 1M * output_cost)
        """
        prompt_tokens = context.features.prompt_tokens_estimated
        out_tokens = context.complexity.estimated_output_tokens
        in_cost = (prompt_tokens / 1_000_000) * model.input_cost_per_million
        out_cost = (out_tokens / 1_000_000) * model.output_cost_per_million
        return round(in_cost + out_cost, 8)

    @staticmethod
    def _load_config(path: str) -> Dict[str, Any]:
        with open(path, "r", encoding="utf-8") as fh:
            return yaml.safe_load(fh)
