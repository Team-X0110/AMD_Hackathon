"""routing — Token-efficient dynamic model routing."""
from src.routing.engine import DynamicRoutingEngine, get_routing_engine
from src.routing.models import RouteDecision, RouteOutcome, RouteTier, TokenUsage

__all__ = [
    "DynamicRoutingEngine",
    "RouteDecision",
    "RouteOutcome",
    "RouteTier",
    "TokenUsage",
    "get_routing_engine",
]
