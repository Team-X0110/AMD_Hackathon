"""
reflection/retry_history.py
============================
Immutable append-only retry attempt log for one reflection session.

The history provides:
- Ordered record of all attempts (for audit trail)
- Aggregate statistics (total tokens, cost, latency)
- Detection of infinite loops (same model + same action repeated too many times)

Thread safety: A threading.Lock is used, but the Reflection Agent is expected
to run in a single thread per request.  The lock is defensive.
"""

from __future__ import annotations

import logging
import threading
from typing import Dict, List, Optional, Tuple

from core.interfaces import IRetryHistory
from core.types import FailureCategory, ReflectionAction, RetryAttempt

logger = logging.getLogger(__name__)


class RetryHistory(IRetryHistory):
    """
    Append-only, in-memory retry attempt log for a single reflection session.

    Args:
        local_cost_per_token: Cost per token for local calls (default 0.0).
        fireworks_cost_per_token: Fallback per-token cost for Fireworks calls
            when the model's actual cost is unknown (default 0.000002 = $2/1M).
    """

    def __init__(
        self,
        local_cost_per_token: float = 0.0,
        fireworks_cost_per_token: float = 0.000002,
    ) -> None:
        self._attempts: List[RetryAttempt] = []
        self._lock = threading.RLock()
        self._local_cost_per_token = local_cost_per_token
        self._fireworks_cost_per_token = fireworks_cost_per_token

    # ------------------------------------------------------------------
    # IRetryHistory implementation
    # ------------------------------------------------------------------

    def record(self, attempt: RetryAttempt) -> None:
        """
        Append a RetryAttempt.  Thread-safe.

        Args:
            attempt: The completed retry attempt to record.
        """
        with self._lock:
            self._attempts.append(attempt)
            logger.debug(
                "retry_attempt_recorded",
                extra={
                    "attempt_number": attempt.attempt_number,
                    "model_id": attempt.model_id,
                    "action": attempt.action_taken.value,
                    "success": attempt.success,
                    "tokens": attempt.estimated_tokens_used,
                    "latency_ms": round(attempt.latency_ms, 2),
                },
            )

    def get_all(self) -> List[RetryAttempt]:
        """Return all recorded attempts in chronological order (snapshot)."""
        with self._lock:
            return list(self._attempts)

    def get_total_retries(self) -> int:
        """Return total number of attempts recorded."""
        with self._lock:
            return len(self._attempts)

    def get_total_tokens(self) -> int:
        """Return sum of estimated_tokens_used across all attempts."""
        with self._lock:
            return sum(a.estimated_tokens_used for a in self._attempts)

    def get_total_cost(self) -> float:
        """
        Return estimated total Fireworks cost in USD across all attempts.
        Local attempts contribute $0.
        """
        with self._lock:
            total = 0.0
            for attempt in self._attempts:
                if not attempt.is_local:
                    total += (
                        attempt.estimated_tokens_used * self._fireworks_cost_per_token
                    )
            return round(total, 8)

    def get_total_latency_ms(self) -> float:
        """Return sum of latency_ms across all attempts."""
        with self._lock:
            return sum(a.latency_ms for a in self._attempts)

    # ------------------------------------------------------------------
    # ADDITIONAL QUERY METHODS
    # ------------------------------------------------------------------

    def get_local_attempt_count(self) -> int:
        """Return number of attempts made on the local model."""
        with self._lock:
            return sum(1 for a in self._attempts if a.is_local)

    def get_fireworks_attempt_count(self) -> int:
        """Return number of attempts made on Fireworks models."""
        with self._lock:
            return sum(1 for a in self._attempts if not a.is_local)

    def get_escalation_count(self) -> int:
        """Return number of escalation actions taken."""
        escalation_actions = {
            ReflectionAction.ESCALATE,
            ReflectionAction.ESCALATE_AFTER_RETRY,
            ReflectionAction.RETRY_CODING_MODEL,
        }
        with self._lock:
            return sum(
                1 for a in self._attempts if a.action_taken in escalation_actions
            )

    def has_infinite_loop(
        self,
        model_id: str,
        action: ReflectionAction,
        max_repeat: int = 2,
    ) -> bool:
        """
        Return True if the same (model_id, action) pair has occurred more than
        max_repeat times — a strong signal of an infinite retry loop.

        Args:
            model_id: Model to check.
            action: Action to check.
            max_repeat: Maximum allowed repetitions of this pair.
        """
        with self._lock:
            count = sum(
                1
                for a in self._attempts
                if a.model_id == model_id and a.action_taken == action
            )
            return count >= max_repeat

    def get_failure_category_counts(self) -> Dict[str, int]:
        """Return a count of each FailureCategory seen across all attempts."""
        with self._lock:
            counts: Dict[str, int] = {}
            for attempt in self._attempts:
                key = attempt.failure_category.value
                counts[key] = counts.get(key, 0) + 1
            return counts

    def get_last_attempt(self) -> Optional[RetryAttempt]:
        """Return the most recent attempt, or None if history is empty."""
        with self._lock:
            return self._attempts[-1] if self._attempts else None

    def get_best_verification_score(self) -> Optional[float]:
        """Return the highest verification score seen across all attempts."""
        with self._lock:
            scores = [
                a.verification_score_after
                for a in self._attempts
                if a.verification_score_after is not None
            ]
            return max(scores) if scores else None

    def get_models_tried(self) -> List[str]:
        """Return list of model IDs tried (in order, may contain duplicates)."""
        with self._lock:
            return [a.model_id for a in self._attempts]

    def summarise(self) -> Dict[str, object]:
        """
        Return a summary dict suitable for telemetry or debugging.

        Keys match ExecutionRecord field names for easy merging.
        """
        with self._lock:
            return {
                "total_retries": len(self._attempts),
                "total_escalations": self.get_escalation_count(),
                "local_calls": self.get_local_attempt_count(),
                "fireworks_calls": self.get_fireworks_attempt_count(),
                "failure_categories_seen": list(self.get_failure_category_counts().keys()),
                "total_tokens_used": self.get_total_tokens(),
                "total_cost_usd": self.get_total_cost(),
                "total_latency_ms": self.get_total_latency_ms(),
                "best_verification_score": self.get_best_verification_score(),
                "models_tried": self.get_models_tried(),
            }
