"""
agents/prompt_refinement.py — Prompt Refinement Agent.

Takes a raw, potentially messy or ambiguous user prompt and rewrites it
to be clear, actionable, and formatted nicely for the downstream agents.
"""
from __future__ import annotations

from src.routing.engine import get_routing_engine
from src.validators import validate_refinement_schema

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
    engine = get_routing_engine()
    result, token_usage, outcomes = engine.execute_with_escalation(
        agent="refinement",
        text=user_prompt,
        system_prompt=REFINEMENT_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        validate_fn=validate_refinement_schema,
    )
    routing = [o.model_dump() for o in outcomes]
    
    return {
        "refinement": result,
        "tokens_used": token_usage.total_tokens,
        "fireworks_tokens": token_usage.fireworks_tokens,
        "routing": routing,
    }
