"""
agents/prompt_refinement.py — Prompt Refinement Agent.

Takes a raw, potentially messy or ambiguous user prompt and rewrites it
to be clear, actionable, and formatted nicely for the downstream agents.
"""
from __future__ import annotations

from src.integration import build_routing_context, execute_with_reflection
from core.types import TaskType

REFINEMENT_SYSTEM_PROMPT = """You are a Prompt Refinement Agent. 
Your job is to take a raw user request and rewrite it to be clear, actionable, and free of typos. 
Resolve obvious ambiguity where possible, but do not change the core intent.

Return a JSON object with EXACTLY these keys:

{
  "refined_prompt": "<the rewritten, clear prompt>",
  "ambiguity_resolved": <true or false, whether you had to guess intent due to vagueness>,
  "changes_made": ["<brief description of a change you made>"]
}

Rules:
- Output ONLY the JSON object. No prose, no markdown fences, no explanation.
- 'changes_made' must be a list (can be empty []).
- 'ambiguity_resolved' must be a boolean (true/false).
"""

def refine_prompt(user_prompt: str) -> dict:
    """
    Executes the routed LLM call to refine a prompt.
    Returns:
        {"refinement": dict, "tokens_used": int, "fireworks_tokens": int, "routing": list}
    """
    context = build_routing_context(user_prompt, REFINEMENT_SYSTEM_PROMPT, TaskType.GENERAL_CHAT, expected_output_format="json")
    outcome = execute_with_reflection(context)
    
    result = outcome["result"]
    total_tokens = outcome["tokens_used"]
    fw_tokens = total_tokens if outcome["routing_metrics"]["routed_tier"] != "LOCAL" else 0
    routing = [outcome["routing_metrics"]]
    
    return {
        "refinement": result,
        "tokens_used": total_tokens,
        "fireworks_tokens": fw_tokens,
        "routing": routing,
    }
