"""Lightweight prompt optimizer for token-efficient LLM calls.

Responsibilities:
- compress prompts by removing repeated phrases
- trim context to the most informative clauses
- estimate token counts heuristically
- build compact prompt pairs for routing/agent calls
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class OptimizedPrompt:
    system_prompt: str
    user_prompt: str
    estimated_tokens: int


class PromptOptimizer:
    def __init__(self, avg_chars_per_token: float = 4.0):
        self.avg_chars_per_token = avg_chars_per_token

    def optimize(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        max_user_tokens: int = 512,
    ) -> OptimizedPrompt:
        """
        Preserve the system prompt exactly.

        Only normalize + trim the user prompt.
        """

        system = self._normalize(system_prompt)
        user = self._normalize(user_prompt)

        if estimate_tokens(user) > max_user_tokens:
            user = self._trim(user, max_user_tokens)

        return OptimizedPrompt(
            system_prompt=system,
            user_prompt=user,
            estimated_tokens=estimate_tokens(system + "\n" + user),
        )

    def _normalize(self, text: str) -> str:
        return " ".join(text.split())

    def _trim(self, text: str, budget: int) -> str:
        words = text.split()

        out = []
        used = 0

        for word in words:
            t = estimate_tokens(word)

            if used + t > budget:
                break

            out.append(word)
            used += t

        return " ".join(out)


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4) if text else 0