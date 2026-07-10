"""
routing/escalation_policy.py
=============================
Progressive tier escalation policy for the Routing Engine.

Tier order (cheapest → most capable):
    0  LOCAL         — Ollama (zero Fireworks tokens)
    1  CHEAP         — Fast, low-cost Fireworks models
    2  BALANCED      — Mid-tier models (quality + cost balance)
    3  PREMIUM       — High-quality Fireworks models
    4  ULTRA_PREMIUM — Frontier models (max accuracy, max cost)

Rules (all loaded from routing_config.yaml):
    - Never skip LOCAL unless vision is required or config disables it.
    - Skip CHEAP for EXPERT complexity tasks or CRITICAL risk.
    - Respect force_escalate_to from the Confidence Engine.
    - Require minimum confidence per tier before attempting it.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import yaml

from core.interfaces import IEscalationPolicy
from core.types import ComplexityLevel, ExecutionTier, RiskLevel, RoutingContext

logger = logging.getLogger(__name__)


class EscalationPolicy(IEscalationPolicy):
    """
    Determines which tier to start at and how to escalate on failure.

    Args:
        routing_config_path: Path to routing_config.yaml.
    """

    def __init__(self, routing_config_path: str) -> None:
        cfg = self._load_config(routing_config_path)
        self._tiers: List[Dict[str, Any]] = cfg.get("escalation_tiers", [])
        self._skip_rules: Dict[str, Any] = cfg.get("tier_skip_rules", {})
        self._local_cfg: Dict[str, Any] = cfg.get("local_execution", {})

        # Build bidirectional maps
        self._order_to_label: Dict[int, str] = {
            t["order"]: t["tier"] for t in self._tiers
        }
        self._label_to_order: Dict[str, int] = {
            t["tier"]: t["order"] for t in self._tiers
        }
        self._min_confidence: Dict[str, float] = self._skip_rules.get(
            "min_confidence_per_tier", {}
        )

    # ------------------------------------------------------------------
    # IEscalationPolicy implementation
    # ------------------------------------------------------------------

    def get_starting_tier_order(self, context: RoutingContext) -> int:
        """
        Return the lowest tier order that should be attempted first.

        Respects force_escalate_to from the Confidence Engine and all
        skip rules from routing_config.yaml.
        """
        # If Confidence Engine forces a specific tier, start there
        force = context.confidence.force_escalate_to
        if force is not None:
            forced_order = self._label_to_order.get(force.value, 0)
            logger.info(
                "escalation_forced",
                extra={"forced_tier": force.value, "request_id": context.request_id},
            )
            return forced_order

        # Otherwise start at LOCAL and walk up to the first non-skipped tier
        for tier_def in sorted(self._tiers, key=lambda t: t["order"]):
            tier_order = tier_def["order"]
            if not self.should_skip_tier(tier_order, context):
                return tier_order

        # Fallback: start at CHEAP (order=1)
        return 1

    def get_next_tier_order(
        self,
        current_tier_order: int,
        context: RoutingContext,
    ) -> Optional[int]:
        """
        Return the next viable tier order after current_tier_order, or None.

        Skips tiers that fail skip rules.
        """
        sorted_tiers = sorted(self._tiers, key=lambda t: t["order"])
        for tier_def in sorted_tiers:
            tier_order = tier_def["order"]
            if tier_order <= current_tier_order:
                continue
            if not self.should_skip_tier(tier_order, context):
                return tier_order
        return None  # No higher tier available

    def should_skip_tier(self, tier_order: int, context: RoutingContext) -> bool:
        """
        Return True if this tier should be bypassed for the given context.

        Checks:
        1. Minimum confidence threshold per tier.
        2. skip_local_if_vision — skip LOCAL if task needs vision.
        3. skip_cheap_if_expert — skip CHEAP for EXPERT tasks.
        4. skip_cheap_if_critical_risk — skip CHEAP for CRITICAL risk.
        """
        tier_label = self._order_to_label.get(tier_order, "")
        task_conf = context.confidence.overall_confidence

        # Minimum confidence gate
        min_conf = self._min_confidence.get(tier_label, 0.0)
        if task_conf < min_conf:
            logger.debug(
                "tier_skipped_low_confidence",
                extra={
                    "tier": tier_label,
                    "task_confidence": task_conf,
                    "min_required": min_conf,
                    "request_id": context.request_id,
                },
            )
            return True

        # LOCAL-specific rules
        if tier_order == 0:  # LOCAL
            if (
                self._skip_rules.get("skip_local_if_vision", True)
                and context.complexity.requires_vision
            ):
                logger.debug(
                    "tier_skipped_vision_required",
                    extra={"tier": "LOCAL", "request_id": context.request_id},
                )
                return True

        # CHEAP-specific rules
        if tier_order == 1:  # CHEAP
            if (
                self._skip_rules.get("skip_cheap_if_expert", True)
                and context.complexity.complexity_level == ComplexityLevel.EXPERT
            ):
                return True
            if (
                self._skip_rules.get("skip_cheap_if_critical_risk", True)
                and context.complexity.risk_level == RiskLevel.CRITICAL
            ):
                return True

        return False

    def tier_order_to_label(self, tier_order: int) -> str:
        """Convert numeric tier order to string label."""
        return self._order_to_label.get(tier_order, "UNKNOWN")

    def tier_label_to_order(self, tier_label: str) -> int:
        """Convert string tier label to numeric order."""
        return self._label_to_order.get(tier_label, 2)

    def get_local_min_confidence(self) -> float:
        """Return the minimum confidence threshold for local execution."""
        return float(
            self._local_cfg.get(
                "min_confidence_threshold",
                self._min_confidence.get("LOCAL", 0.60),
            )
        )

    def get_max_local_retries(self) -> int:
        """Return maximum retries allowed on the local model."""
        return int(self._local_cfg.get("max_retries_local", 2))

    @staticmethod
    def _load_config(path: str) -> Dict[str, Any]:
        with open(path, "r", encoding="utf-8") as fh:
            return yaml.safe_load(fh)
