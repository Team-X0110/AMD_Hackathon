"""
verification/strategies/citation_validator.py
==============================================
Citation presence and plausibility checker.

Activated only when RoutingContext.features.requires_citations is True.

Checks:
1. At least one citation marker is present (e.g. [1], (Author, 2024), URLs).
2. Citation markers are plausible (not random brackets).
3. Minimum citation count met (from config).

No LLM calls are made — pure regex analysis.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Tuple

from core.types import RoutingContext, StrategyResult
from verification.strategies.base_strategy import BaseVerificationStrategy

logger = logging.getLogger(__name__)

# Citation pattern matchers (ordered by reliability)
_CITATION_PATTERNS: List[Tuple[str, re.Pattern]] = [
    ("numbered_bracket", re.compile(r"\[\d+\]")),           # [1], [23]
    ("author_year",      re.compile(r"\([A-Z][a-z]+,?\s+\d{4}\)")),  # (Smith, 2023)
    ("footnote",         re.compile(r"\^\d+\^|\[\^[\w]+\]")),         # ^1^ or [^ref]
    ("url",              re.compile(r"https?://[^\s)>\]\"']{10,}")),   # http(s) URLs
    ("doi",              re.compile(r"10\.\d{4,}/\S+")),              # DOI
    ("ibid_et_al",       re.compile(r"\bet\s+al\.\b", re.I)),         # et al.
]


class CitationValidatorStrategy(BaseVerificationStrategy):
    """
    Validates citation presence when citations are required.

    Args:
        config: Strategy config from verifier_config.yaml.
    """

    def __init__(self, config: Dict[str, Any]) -> None:
        super().__init__(config)
        self._name = "citation_validator"
        self._run_only_if_required: bool = bool(
            config.get("run_only_if_required", True)
        )
        self._min_citations: int = int(config.get("min_citations", 1))

    def should_run(
        self,
        context: RoutingContext,
        response: str,
        model_id: str,
    ) -> bool:
        """Run only when citations are required (unless configured otherwise)."""
        if self._run_only_if_required:
            return context.features.requires_citations
        return True

    def _run_check(
        self,
        context: RoutingContext,
        response: str,
        model_id: str,
    ) -> StrategyResult:
        """Detect and count citations in the response."""
        failure_reasons: List[str] = []
        metadata: Dict[str, Any] = {}

        found_citations: Dict[str, List[str]] = {}
        total_count = 0

        for pattern_name, pattern in _CITATION_PATTERNS:
            matches = pattern.findall(response)
            if matches:
                found_citations[pattern_name] = matches[:10]  # Cap stored matches
                total_count += len(matches)

        metadata["citation_types_found"] = list(found_citations.keys())
        metadata["total_citations_detected"] = total_count
        metadata["min_required"] = self._min_citations
        metadata["examples"] = {
            k: v[:3] for k, v in found_citations.items()
        }

        if total_count < self._min_citations:
            failure_reasons.append(
                f"Insufficient citations: found {total_count}, "
                f"required ≥ {self._min_citations}. "
                f"Expected citation markers such as [1], (Author, 2024), or URLs."
            )

        # Score proportional to citation count relative to minimum
        if self._min_citations > 0:
            score = min(total_count / self._min_citations, 1.0)
        else:
            score = 1.0 if total_count > 0 else 0.5

        # Bonus for multiple citation types (more reliable sourcing)
        if len(found_citations) > 1:
            score = min(score + 0.1, 1.0)

        passed = total_count >= self._min_citations

        return self._make_result(
            passed=passed,
            score=score,
            confidence=0.85,
            failure_reasons=failure_reasons,
            metadata=metadata,
        )
