import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional

# Add the root directory to sys.path so we can import the new modules
import sys
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from core.types import RoutingContext, RoutingDecision, VerificationResult, TaskType, ComplexityLevel, RiskLevel, ExecutionTier
from core.types import FeatureExtractionResult, ComplexityEstimationResult, ConfidenceEngineResult
from routing.routing_engine import RoutingEngine
from verification.verifier import Verifier
from reflection.reflection_agent import ReflectionAgent
from telemetry.telemetry_store import TelemetryStore
from src.fireworks_client import call_inference_raw
from src.agents.feature_extractor import FeatureExtractor as LegacyFeatureExtractor

logger = logging.getLogger(__name__)

# Config paths
MODELS_JSON_PATH = str(ROOT_DIR / "model_data" / "models.json")
ROUTING_CONFIG_PATH = str(ROOT_DIR / "config" / "routing_config.yaml")
VERIFIER_CONFIG_PATH = str(ROOT_DIR / "config" / "verifier_config.yaml")
REFLECTION_CONFIG_PATH = str(ROOT_DIR / "config" / "reflection_config.yaml")
TELEMETRY_LOG_PATH = str(ROOT_DIR / "hybrid-router-cache" / "logs" / "routing_telemetry.jsonl")

# Initialize telemetry
telemetry_store = TelemetryStore(TELEMETRY_LOG_PATH)

# Initialize engines
routing_engine = RoutingEngine(
    models_json_path=MODELS_JSON_PATH,
    routing_config_path=ROUTING_CONFIG_PATH,
    telemetry_store=telemetry_store,
)

# Initialize legacy feature extractor
legacy_extractor = LegacyFeatureExtractor()

def build_routing_context(user_prompt: str, system_prompt: str, task_type: TaskType = TaskType.GENERAL_CHAT, expected_output_format: Optional[str] = None) -> RoutingContext:
    """Builds a typed RoutingContext using mocked/legacy heuristics."""
    legacy_features = legacy_extractor.extract(user_prompt)
    
    # 1. FeatureExtractionResult
    features = FeatureExtractionResult(
        request_id="mock-req-" + str(id(user_prompt)),
        prompt=user_prompt,
        prompt_tokens_estimated=legacy_features["word_count"] * 2,
        detected_task_types=[task_type],
        primary_task_type=task_type,
        has_code_block=legacy_features["has_code_block"],
        has_image=False,
        has_structured_output_requirement=legacy_features["requires_json"],
        requires_citations=False,
        expected_output_format=expected_output_format if expected_output_format else ("json" if legacy_features["requires_json"] else "text"),
        detected_language="en",
        domain_keywords=[],
        tool_schemas_provided=False,
    )
    
    # 2. ComplexityEstimationResult
    is_complex = legacy_features["is_complex"]
    complexity = ComplexityEstimationResult(
        request_id="mock-req",
        complexity_level=ComplexityLevel.COMPLEX if is_complex else ComplexityLevel.SIMPLE,
        complexity_score=0.8 if is_complex else 0.2,
        risk_level=RiskLevel.LOW,
        risk_score=0.1,
        requires_reasoning=is_complex,
        requires_vision=False,
        requires_coding=legacy_features["has_code_block"],
        requires_long_context=features.prompt_tokens_estimated > 4000,
        estimated_output_tokens=512,
        domain=legacy_features["domain"]
    )
    
    # 3. ConfidenceEngineResult
    confidence = ConfidenceEngineResult(
        request_id="mock-req",
        overall_confidence=0.9,
        local_can_handle=not is_complex,
        local_confidence=0.5 if is_complex else 0.9,
        recommended_min_tier=ExecutionTier.LOCAL if not is_complex else ExecutionTier.CHEAP,
        force_escalate_to=None,
        confidence_reasoning="Mocked confidence"
    )
    
    return RoutingContext(
        request_id="mock-req-" + str(id(user_prompt)),
        features=features,
        complexity=complexity,
        confidence=confidence,
        original_messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        metadata={}
    )

# Inference wrapper for Verifier's SelfConsistency and ReflectionAgent
def inference_fn(model_id: str, api_params: Dict[str, Any], is_local: bool) -> str:
    return call_inference_raw(model_id, api_params, is_local)

# Inference wrapper for Verifier (SelfConsistency expects slightly different signature)
def verifier_inference_fn(model_id: str, prompt: str, params: Dict[str, Any]) -> str:
    # Build api_params assuming the simplest case
    api_params = params.copy()
    api_params["model"] = model_id
    api_params["messages"] = [{"role": "user", "content": prompt}]
    is_local = "local" in model_id.lower() or model_id == "local" # basic check
    
    if is_local:
        from config import LOCAL_MODEL
        api_params["model"] = LOCAL_MODEL
        api_params["stream"] = False
        api_params["format"] = "json"
        
    return call_inference_raw(api_params["model"], api_params, is_local)

verifier = Verifier(
    verifier_config_path=VERIFIER_CONFIG_PATH,
    inference_fn=verifier_inference_fn
)

def route_fn(context: RoutingContext, min_tier_order: int) -> Optional[RoutingDecision]:
    # We use route_for_tier which handles a specific tier, 
    # but ReflectionAgent wants to route for ANY tier >= min_tier_order.
    # We can rely on RoutingEngine's progressive logic by artificially starting there.
    for tier_order in range(min_tier_order, 5): # Up to 4 tiers
        decision = routing_engine.route_for_tier(context, tier_order)
        if decision is not None:
            return decision
    return None

def verify_fn(context: RoutingContext, response: str, model_id: str) -> VerificationResult:
    return verifier.verify(context, response, model_id)

reflection_agent = ReflectionAgent(
    reflection_config_path=REFLECTION_CONFIG_PATH,
    routing_config_path=ROUTING_CONFIG_PATH,
    inference_fn=inference_fn,
    route_fn=route_fn,
    verify_fn=verify_fn,
)

def execute_with_reflection(context: RoutingContext) -> dict:
    """
    Executes the full pipeline: Route -> Infer -> Verify -> Reflect
    Returns a dict containing the final JSON (if parsing succeeds) and metadata.
    """
    decision = routing_engine.route(context)
    
    # 1. Initial inference
    initial_response = inference_fn(
        decision.selected_model_id, 
        decision.api_parameters, 
        decision.is_local
    )
    
    # 2. Initial verification
    verification = verifier.verify(context, initial_response, decision.selected_model_id)
    
    # 3. Reflection if needed
    if verification.status.name != "PASSED":
        reflection_result = reflection_agent.reflect(
            context=context,
            initial_response=initial_response,
            initial_verification=verification,
            initial_routing_decision=decision
        )
        
        final_response_str = reflection_result.final_response
        routing_metrics = {
            "routed_tier": reflection_result.final_model_id,
            "complexity_score": context.complexity.complexity_score,
            "retries": reflection_result.total_retries,
            "escalations": reflection_result.total_escalations,
            "succeeded": reflection_result.succeeded,
            "latency_ms": reflection_result.total_latency_ms
        }
        tokens_used = reflection_result.total_tokens_used
        
        if not reflection_result.succeeded:
            raise RuntimeError(f"Reflection failed: {reflection_result.abort_reason}")
    else:
        final_response_str = initial_response
        routing_metrics = {
            "routed_tier": decision.selected_tier.value,
            "complexity_score": context.complexity.complexity_score,
            "retries": 0,
            "escalations": 0,
            "succeeded": True,
            "latency_ms": 0
        }
        # Approximate tokens if no reflection
        tokens_used = ReflectionAgent._estimate_tokens(context, final_response_str)

    # 4. Parse JSON
    try:
        final_json = json.loads(final_response_str)
    except json.JSONDecodeError:
        # Fallback: extract substring between { and }
        start_idx = final_response_str.find('{')
        end_idx = final_response_str.rfind('}') + 1
        if start_idx != -1 and end_idx != 0:
            try:
                final_json = json.loads(final_response_str[start_idx:end_idx])
            except json.JSONDecodeError:
                raise ValueError(f"Failed to parse final response as JSON: {final_response_str}")
        else:
            raise ValueError(f"Failed to parse final response as JSON: {final_response_str}")

    return {
        "result": final_json,
        "routing_metrics": routing_metrics,
        "tokens_used": tokens_used
    }
