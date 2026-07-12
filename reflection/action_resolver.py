"""
reflection/action_resolver.py
==============================
Maps a FailureCategory to a ReflectionAction using the failure_action_map
from reflection_config.yaml.

Handles:
- Primary action (first occurrence of a failure category)
- Fallback action (when max_retries_before_fallback is exceeded)
- Local-first policy: if currently local, ESCALATE means "move to CHEAP tier"
  rather than immediately going to ULTRA_PREMIUM.
"""

from __future__ import annotations

import logging
from typing import Any, Dict

import yaml

from core.interfaces import IActionResolver
from core.types import FailureCategory, ReflectionAction

logger = logging.getLogger(__name__)


class ActionResolver(IActionResolver):
    """
    Resolves ReflectionAction from FailureCategory + retry state.

    Args:
        reflection_config_path: Path to config/reflection_config.yaml.
    """

    def __init__(self, reflection_config_path: str) -> None:
        with open(reflection_config_path, "r", encoding="utf-8") as fh:
            cfg = yaml.safe_load(fh)
        self._action_map: Dict[str, Dict[str, Any]] = cfg.get(
            "failure_action_map", {}
        )

    # ------------------------------------------------------------------
    # IActionResolver implementation
    # ------------------------------------------------------------------

    def resolve(
        self,
        failure_category: FailureCategory,
        attempt_number: int,
        is_currently_local: bool,
    ) -> ReflectionAction:
        """
        Determine what action to take.

        Decision logic:
        1. Look up the failure_category in the action map.
        2. If attempt_number > max_retries_before_fallback → use fallback_action.
        3. Otherwise → use primary_action.
        4. If ABORT: always ABORT regardless of attempt count.

        Args:
            failure_category: The classified reason for failure.
            attempt_number: How many retries have already been attempted (1-indexed).
            is_currently_local: True if the last attempt was on the local model.

        Returns:
            ReflectionAction to execute.
        """
        cat_key = failure_category.value
        entry = self._action_map.get(cat_key, self._action_map.get("UNKNOWN", {}))

        primary_str: str = entry.get("primary_action", "ESCALATE")
        fallback_str: str = entry.get("fallback_action", "ABORT")
        max_before_fallback: int = int(entry.get("max_retries_before_fallback", 1))

        # ABORT is always terminal
        if primary_str == "ABORT":
            return ReflectionAction.ABORT

        # Choose primary vs fallback based on attempt count
        if attempt_number > max_before_fallback:
            action_str = fallback_str
        else:
            action_str = primary_str

        try:
            action = ReflectionAction(action_str)
        except ValueError:
            logger.error(
                "action_resolver_unknown_action",
                extra={"action_str": action_str, "category": cat_key},
            )
            action = ReflectionAction.ESCALATE

        logger.debug(
            "action_resolved",
            extra={
                "failure_category": cat_key,
                "attempt_number": attempt_number,
                "is_local": is_currently_local,
                "resolved_action": action.value,
            },
        )
        return action

    def get_max_retries_before_fallback(
        self,
        failure_category: FailureCategory,
    ) -> int:
        """
        Return the max_retries_before_fallback value for a category.

        Useful for the Reflection Agent to check loop conditions.

        Args:
            failure_category: Category to query.
        """
        entry = self._action_map.get(
            failure_category.value,
            self._action_map.get("UNKNOWN", {}),
        )
        return int(entry.get("max_retries_before_fallback", 1))
