"""
verification/strategies/base_strategy.py
==========================================
Abstract base class for all verification strategies.

Concrete strategies must:
1. Subclass BaseVerificationStrategy.
2. Set self._name in __init__.
3. Implement should_run() and _run_check().

The base class wraps _run_check() with error handling so that any
unhandled exception produces a structured StrategyResult rather than
propagating up and crashing the Verifier.
"""

from __future__ import annotations

import logging
import time
from abc import abstractmethod
from typing import Any, Dict, List

from core.interfaces import IVerificationStrategy
from core.types import RoutingContext, StrategyResult

logger = logging.getLogger(__name__)


class BaseVerificationStrategy(IVerificationStrategy):
    """
    Base class for all verification strategies.

    Subclasses implement:
        should_run(context, response, model_id) -> bool
        _run_check(context, response, model_id) -> StrategyResult

    The public verify() method calls _run_check() inside a try/except
    to guarantee a StrategyResult is always returned.
    """

    def __init__(self, config: Dict[str, Any]) -> None:
        """
        Args:
            config: Strategy-specific config dict from verifier_config.yaml.
                    The key should match self.name in the strategies section.
        """
        self._config = config
        self._name: str = "base"

    @property
    def name(self) -> str:
        """Unique strategy name matching verifier_config.yaml key."""
        return self._name

    def verify(
        self,
        context: RoutingContext,
        response: str,
        model_id: str,
    ) -> StrategyResult:
        """
        Execute verification with full error isolation.

        Any exception in _run_check is caught, logged, and converted to
        a failed StrategyResult so the Verifier can continue.
        """
        t_start = time.monotonic()
        try:
            result = self._run_check(context, response, model_id)
            elapsed = (time.monotonic() - t_start) * 1000
            logger.debug(
                "strategy_complete",
                extra={
                    "strategy": self._name,
                    "passed": result.passed,
                    "score": round(result.score, 4),
                    "latency_ms": round(elapsed, 2),
                    "request_id": context.request_id,
                },
            )
            return result
        except Exception as exc:
            elapsed = (time.monotonic() - t_start) * 1000
            logger.error(
                "strategy_exception",
                extra={
                    "strategy": self._name,
                    "error": str(exc),
                    "latency_ms": round(elapsed, 2),
                    "request_id": context.request_id,
                },
                exc_info=True,
            )
            return StrategyResult(
                strategy_name=self._name,
                passed=False,
                confidence=0.0,
                score=0.0,
                failure_reasons=[f"Strategy raised exception: {type(exc).__name__}: {exc}"],
                metadata={"exception_type": type(exc).__name__},
            )

    @abstractmethod
    def should_run(
        self,
        context: RoutingContext,
        response: str,
        model_id: str,
    ) -> bool:
        """Return True if this strategy applies to the current context."""

    @abstractmethod
    def _run_check(
        self,
        context: RoutingContext,
        response: str,
        model_id: str,
    ) -> StrategyResult:
        """
        Execute the verification logic.

        Must return a StrategyResult.  Must NOT raise unhandled exceptions
        (the base class verify() handles that, but defensive coding is expected).
        """

    # ------------------------------------------------------------------
    # SHARED HELPERS available to all strategies
    # ------------------------------------------------------------------

    def _make_result(
        self,
        passed: bool,
        score: float,
        confidence: float,
        failure_reasons: List[str],
        metadata: Dict[str, Any] | None = None,
    ) -> StrategyResult:
        """Convenience factory for StrategyResult objects."""
        return StrategyResult(
            strategy_name=self._name,
            passed=passed,
            confidence=confidence,
            score=max(0.0, min(score, 1.0)),
            failure_reasons=failure_reasons,
            metadata=metadata or {},
        )
