"""
agents/goal_understanding.py — Goal Understanding Agent.

Cache handling has been moved to the top-level Routing Engine in pipeline.py.
This agent is now a pure execution module that receives a dynamically routed 
model tier and returns a validated structured goal.
"""
from __future__ import annotations

from src.config import LOCAL_MODEL, GOAL_MODEL
from src.fireworks_client import call_llm
from src.validators import validate_goal_schema

# ── Which model to use per tier ──────────────────────────────────────────────
def _get_model_for_tier(tier: str) -> str:
    """
    Maps the router's tier decision to active Fireworks Serverless models.
    """
    if tier == "local":
        return LOCAL_MODEL
    elif tier == "small":
        return "accounts/fireworks/models/llama-v3p2-3b-instruct"
    elif tier == "medium":
        return "accounts/fireworks/models/deepseek-v3p1"
    elif tier == "large":
        return "accounts/fireworks/models/glm-5p2"
    
    # Ensure you return GOAL_MODEL in goal_understanding.py 
    # and PLAN_MODEL in task_planning.py for the fallback!
    return GOAL_MODEL


# ── System prompt ─────────────────────────────────────────────────────────────
# Explicit JSON structure so Ollama's "format":"json" mode has a clear template.
GOAL_SYSTEM_PROMPT = """You are a Goal Understanding Agent. Analyze the user's request and return a JSON object with EXACTLY these keys:

{
  "intent": "<concise verb phrase — what the user wants to accomplish>",
  "entities": ["<key noun 1>", "<key noun 2>"],
  "constraints": ["<technical requirement>", "<non-functional concern>"],
  "success_criteria": ["<measurable condition for done>"],
  "domain": "<broad field, e.g. 'software engineering', 'data analysis', 'devops'>",
  "complexity_hint": "<exactly one of: low | medium | high>"
}

Rules:
- Output ONLY the JSON object. No prose, no markdown fences, no explanation.
- 'entities' must be a list (can be empty []).
- 'constraints' must be a list (can be empty []).
- 'success_criteria' must be a non-empty list — at least one measurable outcome.
- 'complexity_hint' must be exactly 'low', 'medium', or 'high'.
- If the input is ambiguous, make a reasonable inference and still return valid JSON."""


# ── Execution ─────────────────────────────────────────────────────────────────

def understand_goal_with_semantic(user_prompt: str, tier: str = "local") -> dict:
    """
    Executes the LLM call using the model tier determined by the RoutingEngine.
    """
    target_model = _get_model_for_tier(tier)
    print(f"[Agent 1] Executing Goal Understanding on Tier: {tier.upper()} | Model: {target_model}")
    
    # Call the LLM
    result, usage = call_llm(tier, target_model, GOAL_SYSTEM_PROMPT, user_prompt)
    
    # Ensure the output matches our expected schema before proceeding
    validate_goal_schema(result)

    return {
        "goal": result,
        "tokens_used": usage.get("total_tokens", 0)
    }