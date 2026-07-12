"""Pydantic models for the dynamic routing engine."""
from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class RouteTier(str, Enum):
    PYTHON = "python"
    LOCAL = "local"
    FIREWORKS_SMALL = "fireworks_small"
    FIREWORKS_MEDIUM = "fireworks_medium"
    FIREWORKS_LARGE = "fireworks_large"


ESCALATION_LADDER: list[RouteTier] = list(RouteTier)

RouteSource = Literal["heuristic", "fireworks_fc", "escalation", "fallback", "local_first"]
OptimizeTarget = Literal["tokens", "latency", "accuracy"]


class RouteDecision(BaseModel):
    tier: RouteTier
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str
    source: RouteSource
    optimize_for: OptimizeTarget = "tokens"
    routing_tokens: int = 0

    @field_validator("reason")
    @classmethod
    def reason_must_not_be_empty(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("route decision reason cannot be empty")
        return cleaned


class TokenUsage(BaseModel):
    fireworks_tokens: int = 0
    local_tokens: int = 0
    routing_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.fireworks_tokens + self.local_tokens + self.routing_tokens

    def add(self, other: "TokenUsage") -> None:
        self.fireworks_tokens += other.fireworks_tokens
        self.local_tokens += other.local_tokens
        self.routing_tokens += other.routing_tokens


class RouteOutcome(BaseModel):
    agent: str
    tier: RouteTier
    success: bool
    validation_failed: bool = False
    latency_ms: float = 0.0
    fireworks_tokens: int = 0
    local_tokens: int = 0
    escalated_from: RouteTier | None = None
    reason: str = ""
    decision_source: RouteSource | None = None
    error_type: str | None = None
