"""
routing/model_registry.py
==========================
Dynamic loader and index for the Fireworks model catalogue (models.json).

Responsibilities:
- Parse models.json without any hardcoded model IDs.
- Normalise all raw scores (0–100 in JSON) to [0.0, 1.0].
- Map routing_tier strings to numeric tier_order using routing_config.yaml.
- Expose query methods used by UtilityScorer and EscalationPolicy.

The registry does NOT know about local Ollama execution — local routing is
handled by the RoutingEngine using the local_execution config block.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from core.interfaces import IModelRegistry
from core.types import ModelProfile

logger = logging.getLogger(__name__)

# Sentinel value meaning "no score available".
_MISSING = float("nan")


class ModelRegistry(IModelRegistry):
    """
    Loads and indexes the Fireworks model catalogue from models.json.

    Args:
        models_json_path: Absolute or relative path to models.json.
        routing_config_path: Absolute or relative path to routing_config.yaml.
            Used to read the escalation_tiers list for tier_order assignment.
    """

    def __init__(
        self,
        models_json_path: str,
        routing_config_path: str,
    ) -> None:
        self._models_json_path = Path(models_json_path)
        self._routing_config_path = Path(routing_config_path)
        self._profiles: List[ModelProfile] = []
        self._index: Dict[str, ModelProfile] = {}
        self._tier_label_to_order: Dict[str, int] = {}
        self._latency_class_scores: Dict[str, float] = {}

    # ------------------------------------------------------------------
    # IModelRegistry implementation
    # ------------------------------------------------------------------

    def load(self) -> None:
        """
        Load models.json and routing_config.yaml, build all ModelProfile objects.

        Raises:
            FileNotFoundError: If either file is absent.
            ValueError: If the JSON / YAML structure is unexpected.
        """
        routing_cfg = self._load_routing_config()
        self._tier_label_to_order = self._build_tier_map(routing_cfg)
        self._latency_class_scores = routing_cfg.get("latency_class_scores", {})

        models_data = self._load_models_json()
        raw_models: List[Dict[str, Any]] = models_data.get("models", [])

        self._profiles = []
        self._index = {}

        for raw in raw_models:
            try:
                profile = self._parse_model(raw)
                self._profiles.append(profile)
                self._index[profile.model_id] = profile
            except Exception as exc:
                model_id = raw.get("identification", {}).get("model_id", "unknown")
                logger.warning(
                    "model_registry_parse_error",
                    extra={"model_id": model_id, "error": str(exc)},
                )

        logger.info(
            "model_registry_loaded",
            extra={"total_models": len(self._profiles)},
        )

    def get_all_profiles(self) -> List[ModelProfile]:
        """Return all loaded ModelProfile objects."""
        return list(self._profiles)

    def get_profile(self, model_id: str) -> Optional[ModelProfile]:
        """Return the ModelProfile for model_id, or None."""
        return self._index.get(model_id)

    def get_models_in_tier(self, tier_label: str) -> List[ModelProfile]:
        """Return all models whose routing_tier matches tier_label."""
        return [p for p in self._profiles if p.routing_tier == tier_label]

    def get_best_coding_model(self, min_coding_score: float) -> Optional[ModelProfile]:
        """
        Return the model with the highest coding_score >= min_coding_score.

        Args:
            min_coding_score: Normalised minimum [0.0, 1.0].
        """
        candidates = [p for p in self._profiles if p.coding_score >= min_coding_score]
        if not candidates:
            return None
        return max(candidates, key=lambda p: p.coding_score)

    # ------------------------------------------------------------------
    # PRIVATE HELPERS
    # ------------------------------------------------------------------

    def _load_routing_config(self) -> Dict[str, Any]:
        if not self._routing_config_path.exists():
            raise FileNotFoundError(
                f"routing_config.yaml not found: {self._routing_config_path}"
            )
        with self._routing_config_path.open("r", encoding="utf-8") as fh:
            return yaml.safe_load(fh)

    def _load_models_json(self) -> Dict[str, Any]:
        if not self._models_json_path.exists():
            raise FileNotFoundError(
                f"models.json not found: {self._models_json_path}"
            )
        with self._models_json_path.open("r", encoding="utf-8") as fh:
            return json.load(fh)

    def _build_tier_map(self, routing_cfg: Dict[str, Any]) -> Dict[str, int]:
        """Build tier_label → tier_order mapping from routing_config.yaml."""
        tier_map: Dict[str, int] = {}
        for tier_def in routing_cfg.get("escalation_tiers", []):
            label = tier_def.get("tier_label", "")
            order = tier_def.get("order", 0)
            tier_map[label] = order
        return tier_map

    def _parse_model(self, raw: Dict[str, Any]) -> ModelProfile:
        """
        Parse a single raw model dict from models.json into a ModelProfile.

        All scores are normalised from their raw ranges to [0.0, 1.0].
        """
        ident = raw.get("identification", {})
        arch = raw.get("architecture", {})
        caps = raw.get("capabilities", {})
        perf = raw.get("performance", {})
        pricing = raw.get("pricing", {})
        quality = raw.get("quality_assessment", {})
        routing_meta = raw.get("routing_metadata", {})
        agent_recs = raw.get("agent_recommendations", {})
        api_params = raw.get("api_parameters", {})
        notes = raw.get("notes", {})

        routing_tier = routing_meta.get("routing_tier", "Balanced")
        tier_order = self._tier_label_to_order.get(routing_tier, 2)

        latency_class: str = perf.get("latency_class", "Unknown") or "Unknown"
        latency_score = self._latency_class_scores.get(latency_class, 0.50)

        # Normalise 0–100 scores to [0.0, 1.0]
        def norm100(val: Any) -> float:
            if val is None:
                return 0.0
            try:
                return max(0.0, min(float(val) / 100.0, 1.0))
            except (TypeError, ValueError):
                return 0.0

        vision_score_raw = routing_meta.get("vision_score")
        vision_score: Optional[float] = norm100(vision_score_raw) if vision_score_raw is not None else None

        # Cost score: inverted normalised cost (cheaper = higher score)
        # cost_score from routing_metadata (0–100, higher = better cost) or derive from pricing
        raw_cost_score = routing_meta.get("cost_score")
        if raw_cost_score is not None:
            cost_score = norm100(raw_cost_score)
        else:
            # Derive: use output_cost as primary driver (lower = better)
            out_cost = float(pricing.get("output_cost") or 5.0)
            cost_score = max(0.0, 1.0 - (out_cost / 5.0))

        # Agent recommendations: normalise 0–10 → 0–1
        def norm10(val: Any) -> Optional[float]:
            if val is None:
                return None
            try:
                return max(0.0, min(float(val) / 10.0, 1.0))
            except (TypeError, ValueError):
                return None

        agent_recs_norm: Dict[str, Optional[float]] = {
            k: norm10(v) for k, v in agent_recs.items()
        }

        return ModelProfile(
            model_id=ident.get("model_id", ""),
            display_name=ident.get("display_name", ""),
            provider=ident.get("provider", ""),
            routing_tier=routing_tier,
            tier_order=tier_order,
            quality_score=norm100(routing_meta.get("quality_score")),
            reasoning_score=norm100(routing_meta.get("reasoning_score")),
            coding_score=norm100(routing_meta.get("coding_score")),
            vision_score=vision_score,
            token_efficiency_score=norm100(routing_meta.get("token_efficiency_score")),
            cost_score=cost_score,
            latency_score=latency_score,
            recommended_confidence_threshold=float(
                routing_meta.get("recommended_confidence_threshold", 0.75)
            ),
            recommended_task_complexity=routing_meta.get(
                "recommended_task_complexity", "Medium"
            ),
            input_cost_per_million=float(pricing.get("input_cost") or 0.0),
            output_cost_per_million=float(pricing.get("output_cost") or 0.0),
            has_vision=bool(caps.get("vision", False)),
            context_window=int(perf.get("context_window") or 0),
            max_output_tokens=int(perf.get("maximum_output_tokens") or 4096),
            preferred_temperature=float(
                routing_meta.get("preferred_temperature", 0.7)
            ),
            preferred_max_tokens=int(
                routing_meta.get("preferred_max_tokens", 2048)
            ),
            preferred_prompt_style=routing_meta.get("preferred_prompt_style", ""),
            agent_recommendations=agent_recs_norm,
            api_parameters={
                k: bool(v)
                for k, v in api_params.items()
                if isinstance(v, bool)
            },
            failure_modes=routing_meta.get("failure_modes"),
            prompt_engineering_tips=routing_meta.get("prompt_engineering_tips"),
            latency_class=latency_class,
        )
