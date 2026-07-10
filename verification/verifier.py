"""
verification/verifier.py
=========================
Local Verifier orchestrator — Module 3.6.

Runs all applicable verification strategies, aggregates their results via
weighted average, and returns a single VerificationResult with full diagnostics.

Design contract:
- NEVER makes Fireworks API calls.
- The only strategy that makes ANY model call is SelfConsistencyStrategy,
  and that injects an inference callable, keeping this module decoupled
  from the HTTP transport layer.
- Strategies are loaded from verifier_config.yaml — no hardcoding.
- Hard minimums are enforced before the weighted score is computed.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

import yaml

from core.interfaces import IVerificationStrategy, IVerifier
from core.types import (
    RoutingContext,
    StrategyResult,
    VerificationResult,
    VerificationStatus,
)
from verification.strategies.citation_validator import CitationValidatorStrategy
from verification.strategies.code_validator import CodeValidatorStrategy
from verification.strategies.completeness_checker import CompletenessCheckerStrategy
from verification.strategies.format_validator import FormatValidatorStrategy
from verification.strategies.hallucination_detector import HallucinationDetectorStrategy
from verification.strategies.schema_validator import SchemaValidatorStrategy
from verification.strategies.self_consistency import SelfConsistencyStrategy

logger = logging.getLogger(__name__)

InferenceCallable = Callable[[str, str, Dict[str, Any]], str]


def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


class Verifier(IVerifier):
    """
    Production Local Verifier.

    Instantiates and runs all enabled verification strategies defined in
    verifier_config.yaml.  Aggregates results into a single VerificationResult.

    Args:
        verifier_config_path: Path to config/verifier_config.yaml.
        inference_fn: Optional callable for the SelfConsistencyStrategy.
            Signature: (model_id: str, prompt: str, params: dict) -> str.
            If None, self_consistency is automatically disabled.
    """

    def __init__(
        self,
        verifier_config_path: str,
        inference_fn: Optional[InferenceCallable] = None,
    ) -> None:
        with open(verifier_config_path, "r", encoding="utf-8") as fh:
            self._cfg = yaml.safe_load(fh)

        self._strategies_cfg: Dict[str, Any] = self._cfg.get("strategies", {})
        self._aggregation_cfg: Dict[str, Any] = self._cfg.get("aggregation", {})
        self._hard_minimums: Dict[str, Any] = self._cfg.get("hard_minimums", {})
        self._escalation_threshold: float = float(
            self._cfg.get("escalation_recommendation_threshold", 0.55)
        )
        self._token_min_cfg: Dict[str, Any] = self._cfg.get("token_minimization", {})
        self._max_extra_calls: int = int(
            self._token_min_cfg.get("max_additional_calls_per_verify", 2)
        )

        self._pass_threshold: float = float(
            self._aggregation_cfg.get("pass_threshold", 0.65)
        )
        self._partial_threshold: float = float(
            self._aggregation_cfg.get("partial_threshold", 0.45)
        )

        # Build strategy registry
        self._strategies: List[IVerificationStrategy] = self._build_strategies(
            inference_fn
        )

        # Pre-compute normalised weights
        self._weights: Dict[str, float] = self._compute_normalised_weights()

    # ------------------------------------------------------------------
    # IVerifier implementation
    # ------------------------------------------------------------------

    def verify(
        self,
        context: RoutingContext,
        response: str,
        model_id: str,
    ) -> VerificationResult:
        """
        Run all applicable strategies and return aggregated VerificationResult.

        Args:
            context: Full routing context.
            response: Model response to verify.
            model_id: ID of the model that produced the response.

        Returns:
            VerificationResult with full diagnostics.
        """
        t_start = time.monotonic()

        # Hard minimum checks first (short-circuit if response is unusable)
        hard_fail_reasons = self._check_hard_minimums(response)
        if hard_fail_reasons:
            elapsed = (time.monotonic() - t_start) * 1000
            logger.warning(
                "verifier_hard_minimum_failed",
                extra={"request_id": context.request_id, "reasons": hard_fail_reasons},
            )
            return self._build_result(
                request_id=context.request_id,
                model_id=model_id,
                strategy_results=[],
                strategies_run=[],
                strategies_skipped=[s.name for s in self._strategies],
                all_failure_reasons=hard_fail_reasons,
                override_status=VerificationStatus.FAILED,
                override_score=0.0,
                override_confidence=1.0,
            )

        # Run each strategy
        strategy_results: List[StrategyResult] = []
        strategies_run: List[str] = []
        strategies_skipped: List[str] = []

        for strategy in self._strategies:
            if strategy.should_run(context, response, model_id):
                result = strategy.verify(context, response, model_id)
                strategy_results.append(result)
                strategies_run.append(strategy.name)
                logger.debug(
                    "strategy_result",
                    extra={
                        "strategy": strategy.name,
                        "passed": result.passed,
                        "score": round(result.score, 4),
                        "request_id": context.request_id,
                    },
                )
            else:
                strategies_skipped.append(strategy.name)

        # Aggregate
        overall_score, overall_confidence = self._aggregate(strategy_results)
        status = self._determine_status(overall_score)
        all_failures = [
            reason
            for sr in strategy_results
            for reason in sr.failure_reasons
        ]

        elapsed = (time.monotonic() - t_start) * 1000
        logger.info(
            "verifier_complete",
            extra={
                "request_id": context.request_id,
                "status": status.value,
                "score": round(overall_score, 4),
                "latency_ms": round(elapsed, 2),
                "strategies_run": len(strategies_run),
            },
        )

        return self._build_result(
            request_id=context.request_id,
            model_id=model_id,
            strategy_results=strategy_results,
            strategies_run=strategies_run,
            strategies_skipped=strategies_skipped,
            all_failure_reasons=all_failures,
            override_status=status,
            override_score=overall_score,
            override_confidence=overall_confidence,
        )

    # ------------------------------------------------------------------
    # PRIVATE HELPERS
    # ------------------------------------------------------------------

    def _build_strategies(
        self,
        inference_fn: Optional[InferenceCallable],
    ) -> List[IVerificationStrategy]:
        """Instantiate all enabled strategies from config."""
        strategies: List[IVerificationStrategy] = []
        cfg = self._strategies_cfg

        if cfg.get("completeness_checker", {}).get("enabled", True):
            strategies.append(
                CompletenessCheckerStrategy(cfg.get("completeness_checker", {}))
            )
        if cfg.get("format_validator", {}).get("enabled", True):
            strategies.append(
                FormatValidatorStrategy(cfg.get("format_validator", {}))
            )
        if cfg.get("hallucination_detector", {}).get("enabled", True):
            strategies.append(
                HallucinationDetectorStrategy(cfg.get("hallucination_detector", {}))
            )
        if cfg.get("schema_validator", {}).get("enabled", True):
            strategies.append(
                SchemaValidatorStrategy(cfg.get("schema_validator", {}))
            )
        if cfg.get("code_validator", {}).get("enabled", True):
            strategies.append(
                CodeValidatorStrategy(cfg.get("code_validator", {}))
            )
        if cfg.get("citation_validator", {}).get("enabled", True):
            strategies.append(
                CitationValidatorStrategy(cfg.get("citation_validator", {}))
            )
        # SelfConsistency requires an inference callable
        if (
            cfg.get("self_consistency", {}).get("enabled", True)
            and inference_fn is not None
        ):
            strategies.append(
                SelfConsistencyStrategy(
                    cfg.get("self_consistency", {}),
                    inference_fn,
                    global_token_limit=self._max_extra_calls,
                )
            )
        elif cfg.get("self_consistency", {}).get("enabled", True):
            logger.info(
                "self_consistency_disabled",
                extra={"reason": "No inference_fn provided"},
            )

        logger.info(
            "verifier_strategies_loaded",
            extra={"count": len(strategies), "names": [s.name for s in strategies]},
        )
        return strategies

    def _compute_normalised_weights(self) -> Dict[str, float]:
        """
        Read per-strategy weights from config and normalise them so they sum to 1.0.
        Only includes *enabled* strategies.
        """
        raw: Dict[str, float] = {}
        for strategy in self._strategies:
            w = float(self._strategies_cfg.get(strategy.name, {}).get("weight", 1.0))
            raw[strategy.name] = w

        total = sum(raw.values())
        if total == 0:
            return {name: 1.0 / len(raw) for name in raw} if raw else {}
        return {name: w / total for name, w in raw.items()}

    def _aggregate(
        self,
        results: List[StrategyResult],
    ) -> tuple[float, float]:
        """
        Weighted-average aggregation of strategy scores and confidences.
        Returns (overall_score, overall_confidence) in [0.0, 1.0].
        """
        if not results:
            return 1.0, 0.5  # No strategies ran — neutral pass with low confidence

        method = self._aggregation_cfg.get("method", "weighted_average")

        if method == "majority_vote":
            passed_count = sum(1 for r in results if r.passed)
            vote_score = passed_count / len(results)
            avg_conf = sum(r.confidence for r in results) / len(results)
            return vote_score, avg_conf

        # Default: weighted average
        total_weight = 0.0
        weighted_score = 0.0
        weighted_conf = 0.0

        for result in results:
            w = self._weights.get(result.strategy_name, 1.0 / len(results))
            weighted_score += w * result.score
            weighted_conf += w * result.confidence
            total_weight += w

        if total_weight == 0:
            return 0.0, 0.0

        return (
            max(0.0, min(weighted_score / total_weight, 1.0)),
            max(0.0, min(weighted_conf / total_weight, 1.0)),
        )

    def _determine_status(self, score: float) -> VerificationStatus:
        """Map a numeric score to a VerificationStatus."""
        if score >= self._pass_threshold:
            return VerificationStatus.PASSED
        elif score >= self._partial_threshold:
            return VerificationStatus.PARTIAL
        else:
            return VerificationStatus.FAILED

    def _check_hard_minimums(self, response: str) -> List[str]:
        """
        Check absolute quality bars.  Returns list of failure reasons if any fail.
        """
        reasons: List[str] = []
        mins = self._hard_minimums

        if mins.get("must_not_be_empty", True) and not response.strip():
            reasons.append("Response is empty")
            return reasons  # Short-circuit; other checks are meaningless

        char_count = len(response.strip())
        min_len = int(mins.get("min_response_length", 5))
        max_len = int(mins.get("max_response_length", 100000))

        if char_count < min_len:
            reasons.append(
                f"Response ({char_count} chars) is below hard minimum ({min_len} chars)"
            )
        if char_count > max_len:
            reasons.append(
                f"Response ({char_count} chars) exceeds hard maximum ({max_len} chars)"
            )
        return reasons

    def _build_result(
        self,
        request_id: str,
        model_id: str,
        strategy_results: List[StrategyResult],
        strategies_run: List[str],
        strategies_skipped: List[str],
        all_failure_reasons: List[str],
        override_status: VerificationStatus,
        override_score: float,
        override_confidence: float,
    ) -> VerificationResult:
        """Assemble a VerificationResult from aggregated data."""
        recommend_escalation = (
            override_confidence < self._escalation_threshold
            or override_status == VerificationStatus.FAILED
        )
        escalation_reason: Optional[str] = None
        if recommend_escalation:
            if override_status == VerificationStatus.FAILED:
                escalation_reason = "Verification failed — response quality below minimum threshold"
            else:
                escalation_reason = (
                    f"Verification confidence {override_confidence:.2%} below "
                    f"escalation threshold {self._escalation_threshold:.2%}"
                )

        return VerificationResult(
            request_id=request_id,
            status=override_status,
            overall_confidence=round(override_confidence, 4),
            overall_score=round(override_score, 4),
            strategy_results=strategy_results,
            failure_reasons=all_failure_reasons,
            recommended_escalation=recommend_escalation,
            recommended_escalation_reason=escalation_reason,
            strategies_run=strategies_run,
            strategies_skipped=strategies_skipped,
            verification_timestamp=_now_utc(),
            model_id_verified=model_id,
        )
