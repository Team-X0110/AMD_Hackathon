"""
agents/response_generation.py — Response Generation Agent.

Generates a friendly, direct conversational markdown response using the routed model.
"""
from __future__ import annotations
import time
import logging
from src.integration import build_routing_context, routing_engine, inference_fn
from core.types import TaskType
from reflection.reflection_agent import ReflectionAgent

logger = logging.getLogger(__name__)

RESPONSE_SYSTEM_PROMPT = """You are a helpful and intelligent AI assistant.
Analyze the user's prompt and answer it directly, accurately, and conversationally.
To ensure your response is highly accurate, here is the structured goal understanding and the task plan:
Goal: {goal}
Plan: {plan}

Rules:
1. Provide a direct, natural, and helpful response to the user's request.
2. Use clean, well-formatted markdown. If code is requested, provide it in a fenced code block with the correct language tag (e.g. ```python).
3. In code examples, write concise idiomatic code. Do NOT add docstrings (triple-quote comment blocks). Do NOT add inline comments unless they are essential for understanding.
4. Do NOT wrap your entire response in a code block. Only put the code itself inside a fenced block.
5. Do NOT output JSON. Output your reply as natural readable text.
"""


def _clean_response(text: str) -> str:
    """Remove outer markdown code-fence wrappers that small local models sometimes add."""
    stripped = text.strip()
    # If the entire response is wrapped in a single code fence, unwrap it
    if stripped.startswith("```") and stripped.endswith("```") and stripped.count("```") == 2:
        # Remove the opening fence line and closing fence
        lines = stripped.splitlines()
        # Drop first line (``` or ```python) and last line (```)
        inner = "\n".join(lines[1:-1])
        return inner.strip()
    return stripped


def generate_response(user_prompt: str, goal: dict, plan: dict) -> dict:
    """Generate a conversational response using the routing decision."""
    # Format the system prompt with the Goal and Plan
    system_prompt = RESPONSE_SYSTEM_PROMPT.format(goal=goal, plan=plan)

    # Build routing context with TaskType.GENERAL_CHAT and expected_output_format="text"
    context = build_routing_context(
        user_prompt, system_prompt, TaskType.GENERAL_CHAT, expected_output_format="text"
    )

    # Determine routing decision
    decision = routing_engine.route(context)

    # Run inference (no reflection/verification needed for direct chat response)
    t0 = time.perf_counter()
    response_text = inference_fn(
        decision.selected_model_id,
        decision.api_parameters,
        decision.is_local,
    )
    latency_ms = (time.perf_counter() - t0) * 1000

    # Post-process: remove unwanted outer wrapping
    cleaned = _clean_response(response_text)

    # Estimate tokens used
    tokens_used = ReflectionAgent._estimate_tokens(context, cleaned)
    fw_tokens = tokens_used if not decision.is_local else 0

    return {
        "response": cleaned,
        "tokens_used": tokens_used,
        "fireworks_tokens": fw_tokens,
        "routing": {
            "routed_tier": decision.selected_tier.value,
            "selected_model_id": decision.selected_model_id,
            "is_local": decision.is_local,
            "latency_ms": latency_ms,
        },
    }
