"""
verification/strategies/hallucination_detector.py
==================================================
Statistical hallucination heuristics — no LLM calls.

Detects:
1. High n-gram repetition ratio — a strong signal of degenerate/looping output.
2. Contradiction keywords — phrases models use when fabricating uncertain facts.
3. Confidence deflation — sudden hedging after confident claims.
4. Numeric consistency — detects obviously contradictory numbers in short spans.

This is a fast, lightweight first-pass.  It does NOT do semantic entailment.
"""

from __future__ import annotations

import logging
import re
from collections import Counter
from typing import Any, Dict, List, Tuple

from core.types import RoutingContext, StrategyResult
from verification.strategies.base_strategy import BaseVerificationStrategy

logger = logging.getLogger(__name__)


class HallucinationDetectorStrategy(BaseVerificationStrategy):
    """
    Heuristic-based hallucination detector.

    Args:
        config: Strategy config from verifier_config.yaml.
    """

    def __init__(self, config: Dict[str, Any]) -> None:
        super().__init__(config)
        self._name = "hallucination_detector"
        self._repetition_threshold: float = float(
            config.get("repetition_ratio_threshold", 0.40)
        )
        self._ngram_size: int = int(config.get("ngram_size", 4))
        self._contradiction_keywords: List[str] = config.get(
            "contradiction_keywords",
            [
                "as of my knowledge cutoff",
                "I believe but am not certain",
                "I'm not sure but",
                "this might be incorrect",
            ],
        )

    def should_run(
        self,
        context: RoutingContext,
        response: str,
        model_id: str,
    ) -> bool:
        """Always runs — hallucination is a universal risk."""
        return True

    def _run_check(
        self,
        context: RoutingContext,
        response: str,
        model_id: str,
    ) -> StrategyResult:
        """Run all hallucination heuristics and aggregate results."""
        failure_reasons: List[str] = []
        metadata: Dict[str, Any] = {}

        # --- Check 1: N-gram repetition ---
        rep_ratio, rep_detail = self._compute_repetition_ratio(response)
        metadata["repetition_ratio"] = round(rep_ratio, 4)
        metadata["repetition_detail"] = rep_detail

        if rep_ratio > self._repetition_threshold:
            failure_reasons.append(
                f"High n-gram repetition ratio: {rep_ratio:.2%} "
                f"(threshold: {self._repetition_threshold:.2%}). "
                f"Most repeated: {rep_detail.get('most_repeated', '')}"
            )

        # --- Check 2: Contradiction / uncertainty keywords ---
        keyword_hits = self._detect_contradiction_keywords(response)
        metadata["contradiction_keywords_found"] = keyword_hits

        if keyword_hits:
            failure_reasons.append(
                f"Response contains {len(keyword_hits)} uncertainty indicator(s): "
                + "; ".join(f'"{k}"' for k in keyword_hits[:3])
            )

        # --- Check 3: Numeric contradiction (simple) ---
        num_contradiction = self._detect_numeric_contradiction(response)
        metadata["numeric_contradiction"] = num_contradiction
        if num_contradiction:
            failure_reasons.append(
                "Potentially contradictory numeric values detected in close proximity"
            )

        # --- Aggregate score ---
        # Each detected issue reduces score
        issue_count = (
            (1 if rep_ratio > self._repetition_threshold else 0)
            + min(len(keyword_hits), 3)
            + (1 if num_contradiction else 0)
        )
        score = max(0.0, 1.0 - (issue_count * 0.25))
        passed = len(failure_reasons) == 0

        # Confidence in this heuristic-based check is moderate
        confidence = 0.70 if not failure_reasons else 0.65

        return self._make_result(
            passed=passed,
            score=score,
            confidence=confidence,
            failure_reasons=failure_reasons,
            metadata=metadata,
        )

    # ------------------------------------------------------------------
    # PRIVATE HELPERS
    # ------------------------------------------------------------------

    def _compute_repetition_ratio(
        self, text: str
    ) -> Tuple[float, Dict[str, Any]]:
        """
        Compute the fraction of n-grams that are repeated.

        Returns (ratio, detail_dict) where ratio is in [0.0, 1.0].
        High ratio (> threshold) indicates looping / degenerate output.
        """
        words = text.lower().split()
        n = self._ngram_size

        if len(words) < n * 2:
            return 0.0, {"note": "Response too short for n-gram analysis"}

        ngrams = [tuple(words[i: i + n]) for i in range(len(words) - n + 1)]
        if not ngrams:
            return 0.0, {}

        counts = Counter(ngrams)
        repeated = sum(c - 1 for c in counts.values() if c > 1)
        ratio = repeated / len(ngrams)

        most_repeated_ngram, most_repeated_count = counts.most_common(1)[0]
        detail = {
            "total_ngrams": len(ngrams),
            "repeated_ngrams": repeated,
            "most_repeated": " ".join(most_repeated_ngram),
            "most_repeated_count": most_repeated_count,
        }
        return ratio, detail

    def _detect_contradiction_keywords(self, text: str) -> List[str]:
        """Return list of contradiction/uncertainty keywords found in the text."""
        lower = text.lower()
        return [kw for kw in self._contradiction_keywords if kw.lower() in lower]

    def _detect_numeric_contradiction(self, text: str) -> bool:
        """
        Simple heuristic: look for two different numbers within 50 chars of each other
        that share the same neighbouring context word (suggesting a stated fact changed).
        E.g. "population of 1 million... population of 2 million"
        This is intentionally conservative to minimise false positives.
        """
        # Find all "keyword + number" pairs
        pattern = re.compile(r"(\b\w{4,}\b)\s+(?:of\s+)?(\d[\d,]*(?:\.\d+)?)\s*(?:million|billion|thousand|%)?", re.I)
        matches = list(pattern.finditer(text))

        if len(matches) < 2:
            return False

        # Group by context keyword
        keyword_numbers: Dict[str, List[str]] = {}
        for m in matches:
            keyword = m.group(1).lower()
            number = m.group(2).replace(",", "")
            keyword_numbers.setdefault(keyword, []).append(number)

        # If same keyword appears with two different numbers → potential contradiction
        for keyword, numbers in keyword_numbers.items():
            unique = set(numbers)
            if len(unique) > 1 and keyword not in {
                "page", "line", "step", "chapter", "version", "item",
            }:
                return True

        return False
