"""
verification/strategies/self_consistency.py
============================================
Self-consistency verification strategy.

Makes `num_samples` additional calls to the SAME model and checks whether
the responses agree with the original.  Agreement is measured by
normalised longest-common-subsequence (LCS) ratio — a lightweight proxy
for semantic similarity that requires no embedding model.

To minimise token cost:
- Only runs for HIGH and CRITICAL risk tasks (configurable).
- Uses a compressed version of the prompt (first 512 chars) for re-sampling.
- Additional calls are capped at max_additional_calls_per_verify from config.

IMPORTANT: This strategy makes real API calls.  The caller (Verifier) is
responsible for passing a callable that abstracts local vs Fireworks routing.
"""

from __future__ import annotations

import difflib
import logging
from typing import Any, Callable, Dict, List, Optional

from core.types import RiskLevel, RoutingContext, StrategyResult
from verification.strategies.base_strategy import BaseVerificationStrategy

logger = logging.getLogger(__name__)

# Signature for the inference callable injected by the Verifier
InferenceCallable = Callable[[str, str, Dict[str, Any]], str]


class SelfConsistencyStrategy(BaseVerificationStrategy):
    """
    Multi-sample self-consistency check.

    Draws additional samples from the same model and measures agreement
    via sequence similarity.  Only activates for high/critical risk tasks
    to avoid unnecessary token spend.

    Args:
        config: Strategy config from verifier_config.yaml.
        inference_fn: Callable(model_id, prompt, api_params) -> response_str.
            Injected so this strategy is decoupled from the HTTP layer.
        global_token_limit: Max additional calls allowed per verification pass
            (from token_minimization.max_additional_calls_per_verify).
    """

    def __init__(
        self,
        config: Dict[str, Any],
        inference_fn: InferenceCallable,
        global_token_limit: int = 2,
    ) -> None:
        super().__init__(config)
        self._name = "self_consistency"
        self._inference_fn = inference_fn
        self._num_samples: int = int(config.get("num_samples", 2))
        self._agreement_threshold: float = float(config.get("agreement_threshold", 0.75))
        self._only_on_high_risk: bool = bool(config.get("only_on_high_risk", True))
        self._global_token_limit = global_token_limit
        # Respect global cap
        self._effective_samples = min(self._num_samples, self._global_token_limit)

    def should_run(
        self,
        context: RoutingContext,
        response: str,
        model_id: str,
    ) -> bool:
        """
        Only run for HIGH/CRITICAL risk tasks (when only_on_high_risk=True).
        Skip entirely for local model (no additional cost benefit analysis needed).
        """
        if model_id == "local":
            return False
        if self._only_on_high_risk:
            risk = context.complexity.risk_level
            return risk in (RiskLevel.HIGH, RiskLevel.CRITICAL)
        return True

    def _run_check(
        self,
        context: RoutingContext,
        response: str,
        model_id: str,
    ) -> StrategyResult:
        """
        Draw additional samples and measure agreement with the original response.
        """
        samples: List[str] = []
        errors: List[str] = []

        # Build a compact prompt for re-sampling (trim to 512 chars to save tokens)
        prompt_text = context.features.prompt[:512]

        for i in range(self._effective_samples):
            try:
                api_params: Dict[str, Any] = {
                    "temperature": 0.7,
                    "max_tokens": min(512, context.complexity.estimated_output_tokens),
                }
                sample = self._inference_fn(model_id, prompt_text, api_params)
                if sample:
                    samples.append(sample)
            except Exception as exc:
                errors.append(f"Sample {i+1} failed: {exc}")
                logger.warning(
                    "self_consistency_sample_failed",
                    extra={"sample_idx": i, "error": str(exc), "request_id": context.request_id},
                )

        if not samples:
            reason = "No additional samples could be obtained"
            if errors:
                reason += f": {errors[0]}"
            return self._make_result(
                passed=False,
                score=0.0,
                confidence=0.2,
                failure_reasons=[reason],
                metadata={"errors": errors},
            )

        # Measure similarity of each sample to the original
        similarities = [
            difflib.SequenceMatcher(None, response, s).ratio()
            for s in samples
        ]
        avg_similarity = sum(similarities) / len(similarities)
        agreement_rate = sum(
            1 for s in similarities if s >= self._agreement_threshold
        ) / len(similarities)

        passed = agreement_rate >= self._agreement_threshold
        score = avg_similarity
        confidence = 0.8 if len(samples) >= self._effective_samples else 0.5

        failure_reasons: List[str] = []
        if not passed:
            failure_reasons.append(
                f"Self-consistency agreement {agreement_rate:.2%} < "
                f"threshold {self._agreement_threshold:.2%} "
                f"(avg similarity: {avg_similarity:.3f})"
            )

        return self._make_result(
            passed=passed,
            score=score,
            confidence=confidence,
            failure_reasons=failure_reasons,
            metadata={
                "num_samples": len(samples),
                "avg_similarity": round(avg_similarity, 4),
                "agreement_rate": round(agreement_rate, 4),
                "individual_similarities": [round(s, 4) for s in similarities],
                "errors": errors,
            },
        )
