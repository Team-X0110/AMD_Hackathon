"""
verification/strategies/completeness_checker.py
================================================
Checks that the response meets minimum content thresholds.

Verifies:
- Minimum and maximum character length.
- Minimum number of sentences.
- Response is not a refusal / error message.
- Response actually addresses the prompt (basic keyword overlap).

No LLM calls are made — pure text analysis.
"""

from __future__ import annotations

import re
import logging
from typing import Any, Dict, List

from core.types import RoutingContext, StrategyResult
from verification.strategies.base_strategy import BaseVerificationStrategy

logger = logging.getLogger(__name__)

# Sentence boundary (simple heuristic — no NLTK dependency)
_SENTENCE_SPLIT = re.compile(r'(?<=[.!?])\s+')

# Common refusal patterns
_REFUSAL_PATTERNS = [
    re.compile(r"i('m| am) (unable|not able) to", re.I),
    re.compile(r"i (cannot|can't) (help|assist|answer|provide)", re.I),
    re.compile(r"as an ai (language model|assistant)", re.I),
    re.compile(r"i don't have (access|the ability|information)", re.I),
    re.compile(r"i('m| am) sorry[,.]? (but )?i", re.I),
    re.compile(r"this (request|question) (violates|is against)", re.I),
]


class CompletenessCheckerStrategy(BaseVerificationStrategy):
    """
    Validates that the response is substantive, non-empty, and non-refusal.

    Args:
        config: Strategy config from verifier_config.yaml.
    """

    def __init__(self, config: Dict[str, Any]) -> None:
        super().__init__(config)
        self._name = "completeness_checker"
        self._min_chars: int = int(config.get("min_response_chars", 20))
        self._max_chars: int = int(config.get("max_response_chars", 50000))
        self._min_sentences: int = int(config.get("min_sentences", 1))

    def should_run(
        self,
        context: RoutingContext,
        response: str,
        model_id: str,
    ) -> bool:
        """Always runs — completeness is a universal requirement."""
        return True

    def _run_check(
        self,
        context: RoutingContext,
        response: str,
        model_id: str,
    ) -> StrategyResult:
        """Check length, sentence count, refusal patterns, and keyword overlap."""
        failure_reasons: List[str] = []
        metadata: Dict[str, Any] = {}

        stripped = response.strip()
        char_count = len(stripped)
        metadata["char_count"] = char_count

        # --- Length checks ---
        if char_count < self._min_chars:
            failure_reasons.append(
                f"Response too short: {char_count} chars < minimum {self._min_chars}"
            )
        if char_count > self._max_chars:
            failure_reasons.append(
                f"Response too long: {char_count} chars > maximum {self._max_chars}"
            )

        # --- Sentence count ---
        sentences = [s.strip() for s in _SENTENCE_SPLIT.split(stripped) if s.strip()]
        sentence_count = max(len(sentences), 1)
        metadata["sentence_count"] = sentence_count
        if sentence_count < self._min_sentences:
            failure_reasons.append(
                f"Response has {sentence_count} sentence(s); "
                f"minimum required: {self._min_sentences}"
            )

        # --- Refusal detection ---
        is_refusal = any(p.search(stripped) for p in _REFUSAL_PATTERNS)
        metadata["is_refusal"] = is_refusal
        if is_refusal:
            failure_reasons.append(
                "Response appears to be a refusal or inability statement"
            )

        # --- Keyword overlap (prompt vs response) ---
        overlap_score = self._compute_keyword_overlap(
            context.features.prompt, stripped
        )
        metadata["keyword_overlap_score"] = round(overlap_score, 4)
        if overlap_score < 0.05 and char_count > 50:
            # Very low overlap AND non-trivial response = likely hallucinated topic
            failure_reasons.append(
                f"Low keyword overlap between prompt and response: {overlap_score:.2%}"
            )

        # Score is the average of normalised sub-scores
        length_score = self._length_score(char_count)
        refusal_score = 0.0 if is_refusal else 1.0
        overlap_component = min(overlap_score * 5, 1.0)  # Boost small overlaps
        sentence_score = min(sentence_count / max(self._min_sentences, 1), 1.0)

        score = (length_score + refusal_score + overlap_component + sentence_score) / 4.0
        passed = len(failure_reasons) == 0

        return self._make_result(
            passed=passed,
            score=score,
            confidence=0.85,
            failure_reasons=failure_reasons,
            metadata=metadata,
        )

    # ------------------------------------------------------------------
    # PRIVATE HELPERS
    # ------------------------------------------------------------------

    def _length_score(self, char_count: int) -> float:
        """Return a score in [0, 1] based on how well length meets thresholds."""
        if char_count < self._min_chars:
            return char_count / max(self._min_chars, 1)
        if char_count > self._max_chars:
            excess = char_count - self._max_chars
            return max(0.0, 1.0 - (excess / self._max_chars))
        return 1.0

    @staticmethod
    def _compute_keyword_overlap(prompt: str, response: str) -> float:
        """
        Compute normalised word overlap between prompt and response.
        Stopwords are excluded via a minimal inline set.
        Returns a value in [0.0, 1.0].
        """
        _STOPWORDS = {
            "the", "a", "an", "is", "are", "was", "were", "be", "been",
            "being", "have", "has", "had", "do", "does", "did", "will",
            "would", "could", "should", "may", "might", "shall", "can",
            "to", "of", "in", "for", "on", "with", "at", "by", "from",
            "and", "or", "but", "if", "as", "that", "this", "it", "i",
            "you", "he", "she", "we", "they", "what", "which", "who",
            "how", "not", "no", "so", "up", "out", "about", "into",
        }

        def tokenize(text: str):
            return {
                w.lower().strip(".,!?;:\"'")
                for w in text.split()
                if len(w) > 2 and w.lower() not in _STOPWORDS
            }

        prompt_words = tokenize(prompt)
        response_words = tokenize(response)

        if not prompt_words:
            return 1.0  # Empty prompt — no overlap requirement

        overlap = prompt_words & response_words
        return len(overlap) / len(prompt_words)
