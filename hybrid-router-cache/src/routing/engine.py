"""Dynamic routing engine — local-first with validation-gated escalation."""
from __future__ import annotations

import logging
import time
from collections.abc import Callable

import requests

from src.config import (
    LLM_BACKEND,
    LOCAL_MODEL,
    GOAL_MODEL,
    PLAN_MODEL,
    FIREWORKS_API_KEY,
    ROUTE_MODELS,
    ROUTING_ENABLED,
    ROUTING_MAX_ESCALATIONS,
)
from src.fireworks_client import call_llm
from src.routing.escalation import execution_start_tier, next_tier, skip_tier
from src.routing.fireworks_router import route_via_fireworks_fc, should_use_fc
from src.routing.heuristics import score_complexity
from src.prompt_optimizer import PromptOptimizer
from src.routing.learning import get_learned_stats_flat, record_outcome
from src.routing.models import RouteDecision, RouteOutcome, RouteTier, TokenUsage
from src.routing.python_executor import extract_goal_from_prompt

logger = logging.getLogger(__name__)


class DynamicRoutingEngine:
    def __init__(self, *, prompt_optimizer: PromptOptimizer | None = None) -> None:
        self.prompt_optimizer = prompt_optimizer or PromptOptimizer()
    def decide(self, agent: str, text: str) -> RouteDecision:
        learned = get_learned_stats_flat(agent)
        tier, conf, reason, _complexity = score_complexity(text, agent, learned)

        if should_use_fc(conf):
            fc_decision = route_via_fireworks_fc(agent, text, tier, reason)
            if fc_decision is not None:
                return fc_decision

        return RouteDecision(
            tier=tier,
            confidence=conf,
            reason=reason,
            source="heuristic",
            optimize_for="tokens",
            routing_tokens=0,
        )

    def _execute_tier(
        self,
        tier: RouteTier,
        system_prompt: str,
        user_prompt: str,
    ) -> tuple[dict, dict]:
        if tier == RouteTier.PYTHON:
            return extract_goal_from_prompt(user_prompt), {
                "total_tokens": 0,
                "backend": "python",
            }

        if tier == RouteTier.LOCAL:
            return call_llm("local", LOCAL_MODEL, system_prompt, user_prompt)

        route_key = tier.value
        if route_key not in ROUTE_MODELS:
            raise ValueError(f"No model configured for tier {tier}")

        backend, model = ROUTE_MODELS[route_key]
        return call_llm(backend, model, system_prompt, user_prompt)

    def _first_executable_tier(self, decision: RouteDecision, agent: str) -> RouteTier:
        """Choose an executable starting tier respecting backend configuration."""
        if agent == "plan" and decision.tier == RouteTier.PYTHON:
            # Plan agent can't use Python; escalate to the configured backend
            if LLM_BACKEND == "fireworks" and FIREWORKS_API_KEY:
                return RouteTier.FIREWORKS_SMALL
            return RouteTier.LOCAL

        if decision.tier in {
            RouteTier.FIREWORKS_SMALL,
            RouteTier.FIREWORKS_MEDIUM,
            RouteTier.FIREWORKS_LARGE,
        } and not FIREWORKS_API_KEY:
            logger.info(
                "Route %s selected but FIREWORKS_API_KEY is missing; using local fallback",
                decision.tier.value,
            )
            return RouteTier.LOCAL

        # If decision tier is LOCAL but Fireworks is configured, use Fireworks instead
        if decision.tier == RouteTier.LOCAL and LLM_BACKEND == "fireworks" and FIREWORKS_API_KEY:
            return RouteTier.FIREWORKS_SMALL

        return decision.tier

    def _usage_to_token_usage(
        self,
        usage: dict,
        routing_tokens: int = 0,
    ) -> TokenUsage:
        total = usage.get("total_tokens", 0)
        backend = usage.get("backend", "local")
        if backend == "fireworks":
            return TokenUsage(
                fireworks_tokens=total,
                local_tokens=0,
                routing_tokens=routing_tokens,
            )
        if backend == "python":
            return TokenUsage(routing_tokens=routing_tokens)
        return TokenUsage(local_tokens=total, routing_tokens=routing_tokens)

    def execute_with_escalation(
        self,
        agent: str,
        text: str,
        system_prompt: str,
        user_prompt: str,
        validate_fn: Callable[[dict], None],
    ) -> tuple[dict, TokenUsage, list[RouteOutcome]]:
        if not ROUTING_ENABLED:
            return self._legacy_execute(
                agent, system_prompt, user_prompt, validate_fn
            )

        decision = self.decide(agent, text)
        routing_tokens = decision.routing_tokens
        optimized_system, optimized_user = self._optimize_prompts(system_prompt, user_prompt)

        python_confident = (
            agent == "goal"
            and decision.tier == RouteTier.PYTHON
            and decision.confidence >= 0.88
        )
        if decision.source == "heuristic" and decision.optimize_for == "tokens":
            current = execution_start_tier(
                decision.tier,
                agent=agent,
                python_confident=python_confident,
            )
        else:
            current = self._first_executable_tier(decision, agent)

        outcomes: list[RouteOutcome] = []
        total_usage = TokenUsage(routing_tokens=routing_tokens)
        escalated_from: RouteTier | None = None

        for attempt in range(ROUTING_MAX_ESCALATIONS + 1):
            t0 = time.perf_counter()
            attempt_usage = TokenUsage()
            try:
                logger.debug("=" * 20)
                logger.debug("SYSTEM PROMPT")
                logger.debug(optimized_system)
                logger.debug("=" * 20)

                logger.debug("USER PROMPT")
                logger.debug(optimized_user)
                logger.debug("=" * 20)
                result, usage = self._execute_tier(
                    current, optimized_system, optimized_user
                )
                attempt_usage = self._usage_to_token_usage(usage, routing_tokens=0)
                total_usage.add(attempt_usage)
                validate_fn(result)

                latency_ms = (time.perf_counter() - t0) * 1000
                outcome = RouteOutcome(
                    agent=agent,
                    tier=current,
                    success=True,
                    validation_failed=False,
                    latency_ms=latency_ms,
                    fireworks_tokens=attempt_usage.fireworks_tokens,
                    local_tokens=attempt_usage.local_tokens,
                    escalated_from=escalated_from,
                    reason=decision.reason,
                    decision_source=decision.source,
                )
                outcomes.append(outcome)
                record_outcome(outcome)
                return result, total_usage, outcomes

            except ValueError as exc:
                latency_ms = (time.perf_counter() - t0) * 1000
                outcome = RouteOutcome(
                    agent=agent,
                    tier=current,
                    success=False,
                    validation_failed=True,
                    latency_ms=latency_ms,
                    fireworks_tokens=attempt_usage.fireworks_tokens,
                    local_tokens=attempt_usage.local_tokens,
                    escalated_from=escalated_from,
                    reason=f"validation_failed: {exc}",
                    decision_source=decision.source,
                    error_type="validation",
                )
                outcomes.append(outcome)
                record_outcome(outcome)
                escalated_from = current
                nxt = self._next_executable_tier(current)
                if nxt is None or attempt >= ROUTING_MAX_ESCALATIONS:
                    raise
                current = nxt
                continue

            except RuntimeError as e:
                latency_ms = (time.perf_counter() - t0) * 1000
                outcome = RouteOutcome(
                    agent=agent,
                    tier=current,
                    success=False,
                    latency_ms=latency_ms,
                    escalated_from=escalated_from,
                    reason=f"runtime_error: {e}",
                    decision_source=decision.source,
                    error_type="runtime",
                )
                outcomes.append(outcome)
                record_outcome(outcome)
                escalated_from = current

                if "Ollama" in str(e) or "connect" in str(e).lower():
                    nxt = self._skip_to_executable_tier(current)
                else:
                    nxt = self._next_executable_tier(current)

                if nxt is None or attempt >= ROUTING_MAX_ESCALATIONS:
                    raise
                current = nxt
                continue

            except requests.exceptions.ConnectionError:
                latency_ms = (time.perf_counter() - t0) * 1000
                outcome = RouteOutcome(
                    agent=agent,
                    tier=current,
                    success=False,
                    latency_ms=latency_ms,
                    escalated_from=escalated_from,
                    reason="connection_error",
                    decision_source=decision.source,
                    error_type="infrastructure",
                )
                outcomes.append(outcome)
                record_outcome(outcome)
                escalated_from = current
                skipped = self._skip_to_executable_tier(current)
                if skipped is None or attempt >= ROUTING_MAX_ESCALATIONS:
                    raise RuntimeError(
                        "Cannot connect to Ollama at http://localhost:11434. "
                        "Make sure Ollama is running: `ollama serve`"
                    )
                current = skipped
                continue

        raise RuntimeError(f"All routes exhausted for agent={agent}")

    def _optimize_prompts(self, system_prompt: str, user_prompt: str) -> tuple[str, str]:
        optimized = self.prompt_optimizer.optimize(
            system_prompt,
            user_prompt,
            max_user_tokens=256,
        )
        return optimized.system_prompt, optimized.user_prompt

    def _next_executable_tier(self, current: RouteTier) -> RouteTier | None:
        nxt = next_tier(current)
        while nxt is not None and self._fireworks_unavailable(nxt):
            nxt = next_tier(nxt)
        return nxt

    def _skip_to_executable_tier(self, current: RouteTier) -> RouteTier | None:
        skipped = skip_tier(current)
        while skipped is not None and self._fireworks_unavailable(skipped):
            skipped = next_tier(skipped)
        return skipped

    @staticmethod
    def _fireworks_unavailable(tier: RouteTier) -> bool:
        return (
            tier
            in {
                RouteTier.FIREWORKS_SMALL,
                RouteTier.FIREWORKS_MEDIUM,
                RouteTier.FIREWORKS_LARGE,
            }
            and not FIREWORKS_API_KEY
        )

    def _legacy_execute(
        self,
        agent: str,
        system_prompt: str,
        user_prompt: str,
        validate_fn: Callable[[dict], None],
    ) -> tuple[dict, TokenUsage, list[RouteOutcome]]:
        if LLM_BACKEND == "local":
            model = LOCAL_MODEL
        else:
            model = PLAN_MODEL if agent == "plan" else GOAL_MODEL
        result, usage = call_llm(LLM_BACKEND, model, system_prompt, user_prompt)
        validate_fn(result)
        tu = self._usage_to_token_usage(usage)
        return result, tu, []


_engine: DynamicRoutingEngine | None = None


def get_routing_engine() -> DynamicRoutingEngine:
    global _engine
    if _engine is None:
        _engine = DynamicRoutingEngine()
    return _engine
