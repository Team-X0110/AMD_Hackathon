"""
test_agents_local.py — Test Goal Understanding + Task Planning against local Ollama.

NO Firebase, NO Firestore, NO API keys needed.
Just needs Ollama running with llama3.1:8b pulled.

Usage:
    python test_agents_local.py
"""
import json
import time
import requests

# ── Config ────────────────────────────────────────────────────────────────────
OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL = "llama3.1:8b"
TEMPERATURE = 0.2
TIMEOUT = 120  # seconds — CPU inference can be slow

# ── Prompts ───────────────────────────────────────────────────────────────────
GOAL_SYSTEM_PROMPT = """You are a Goal Understanding Agent. Analyze the user's request and return a JSON object with EXACTLY these keys:

{
  "intent": "<concise verb phrase>",
  "entities": ["<key noun 1>", "<key noun 2>"],
  "constraints": ["<technical requirement>"],
  "success_criteria": ["<measurable condition for done>"],
  "domain": "<broad field>",
  "complexity_hint": "<exactly one of: low | medium | high>"
}

Rules:
- Output ONLY the JSON object. No prose, no markdown fences, no explanation.
- complexity_hint MUST be exactly 'low', 'medium', or 'high'."""

PLAN_SYSTEM_PROMPT = """You are a Task Planning Agent. Given a structured goal JSON, decompose it into an actionable task graph.

Return a JSON object with EXACTLY these top-level keys:

{
  "tasks": [
    {
      "id": "t1",
      "title": "<short action title>",
      "description": "<1-2 sentence explanation>",
      "depends_on": [],
      "estimated_effort": "<one of: S | M | L | XL>"
    }
  ],
  "execution_order": ["t1", "t2"],
  "parallel_groups": [["t2", "t3"]]
}

Rules:
- Output ONLY valid JSON. No prose, no markdown fences.
- Every task must have a unique 'id' (t1, t2, ...).
- 'depends_on' references must only use IDs that exist in 'tasks'.
- The dependency graph must be acyclic (no circular dependencies).
- Maximum 10 tasks. Consolidate if needed.
- estimated_effort: S=hours, M=1-2 days, L=3-5 days, XL=week+"""

# ── Test prompts ──────────────────────────────────────────────────────────────
TEST_PROMPTS = [
    "Build a REST API for a todo app with user authentication and JWT tokens",
    "Create a machine learning pipeline to classify customer support tickets",
    "Set up a CI/CD pipeline for a React app deployed to AWS",
]

SEPARATOR = "-" * 68


# ── Ollama call ───────────────────────────────────────────────────────────────

def call_ollama(system_prompt: str, user_prompt: str, label: str) -> dict:
    """Call local Ollama and return parsed JSON dict."""
    print(f"  Calling Ollama [{label}]...", end=" ", flush=True)
    t0 = time.perf_counter()

    resp = requests.post(
        OLLAMA_URL,
        json={
            "model": MODEL,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_prompt},
            ],
            "stream": False,
            "format": "json",
            "options": {"temperature": TEMPERATURE},
        },
        timeout=TIMEOUT,
    )
    resp.raise_for_status()

    body = resp.json()
    elapsed = time.perf_counter() - t0
    tokens = body.get("prompt_eval_count", 0) + body.get("eval_count", 0)
    print(f"done ({elapsed:.1f}s, {tokens} tokens)")

    return json.loads(body["message"]["content"])


# ── Validation ────────────────────────────────────────────────────────────────

def validate_goal(goal: dict) -> list[str]:
    """Return list of validation errors (empty = OK)."""
    errors = []
    required = {"intent", "entities", "constraints", "success_criteria", "domain", "complexity_hint"}
    missing = required - goal.keys()
    if missing:
        errors.append(f"Missing keys: {sorted(missing)}")
    if goal.get("complexity_hint") not in {"low", "medium", "high"}:
        errors.append(f"Bad complexity_hint: '{goal.get('complexity_hint')}' (must be low/medium/high)")
    if not isinstance(goal.get("success_criteria"), list) or len(goal.get("success_criteria", [])) == 0:
        errors.append("success_criteria must be a non-empty list")
    return errors


def validate_plan(plan: dict) -> list[str]:
    """Return list of validation errors (empty = OK)."""
    errors = []
    if "tasks" not in plan:
        errors.append("Missing 'tasks' key")
        return errors

    ids = {t.get("id") for t in plan["tasks"]}
    for task in plan["tasks"]:
        for dep in task.get("depends_on", []):
            if dep not in ids:
                errors.append(f"Unknown dependency '{dep}' in task '{task.get('id')}'")

    required_task_keys = {"id", "title", "description", "depends_on", "estimated_effort"}
    for t in plan["tasks"]:
        missing = required_task_keys - t.keys()
        if missing:
            errors.append(f"Task '{t.get('id')}' missing keys: {sorted(missing)}")

    return errors


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    # Check Ollama is up first
    try:
        r = requests.get("http://localhost:11434/api/tags", timeout=3)
        r.raise_for_status()
        models = [m["name"] for m in r.json().get("models", [])]
        print(f"\n[OK] Ollama is running. Available models: {models}")
        if not any(MODEL in m for m in models):
            print(f"\n[WARN]  Model '{MODEL}' not found. Pull it with:  ollama pull {MODEL}")
            print("   Then re-run this script.\n")
            return
    except Exception as e:
        print(f"\n[FAIL] Cannot reach Ollama at localhost:11434: {e}")
        print("   Start it with:  ollama serve")
        return

    print(f"\n{'='*68}")
    print(f"  LOCAL AGENT TEST - Goal Understanding + Task Planning")
    print(f"  Model: {MODEL} via Ollama")
    print(f"{'='*68}")

    all_passed = True

    for i, prompt in enumerate(TEST_PROMPTS, 1):
        print(f"\n[{i}/{len(TEST_PROMPTS)}] {prompt[:65]}{'...' if len(prompt) > 65 else ''}")
        print(SEPARATOR)

        # ── Step 1: Goal Understanding ────────────────────────────────────────
        try:
            goal = call_ollama(GOAL_SYSTEM_PROMPT, prompt, "Goal Agent")
        except Exception as e:
            print(f"  [FAIL] Goal agent FAILED: {e}")
            all_passed = False
            continue

        goal_errors = validate_goal(goal)
        if goal_errors:
            print(f"  [WARN]  Goal schema issues: {goal_errors}")
            all_passed = False
        else:
            print(f"  [OK] Goal valid")
            print(f"     intent     : {goal.get('intent')}")
            print(f"     domain     : {goal.get('domain')}")
            print(f"     complexity : {goal.get('complexity_hint')}")
            print(f"     entities   : {goal.get('entities')}")

        # ── Step 2: Task Planning ─────────────────────────────────────────────
        try:
            plan = call_ollama(PLAN_SYSTEM_PROMPT, json.dumps(goal), "Plan Agent")
        except Exception as e:
            print(f"  [FAIL] Plan agent FAILED: {e}")
            all_passed = False
            continue

        plan_errors = validate_plan(plan)
        if plan_errors:
            print(f"  [WARN]  Plan schema issues: {plan_errors}")
            all_passed = False
        else:
            tasks = plan.get("tasks", [])
            print(f"  [OK] Plan valid — {len(tasks)} tasks")
            for t in tasks:
                deps = t.get("depends_on", [])
                dep_str = f" (needs: {deps})" if deps else ""
                print(f"     [{t.get('estimated_effort','?')}] {t.get('id')}: {t.get('title')}{dep_str}")

        # Print raw JSON for inspection
        print(f"\n  --- Raw goal JSON ---")
        print("  " + json.dumps(goal, indent=2).replace("\n", "\n  "))
        print(f"\n  --- Raw plan JSON (tasks only) ---")
        print("  " + json.dumps({"tasks": plan.get("tasks", [])}, indent=2).replace("\n", "\n  "))

    print(f"\n{'='*68}")
    if all_passed:
        print(f"  [OK] ALL TESTS PASSED — agents working locally on {MODEL}")
    else:
        print(f"  [WARN]  Some tests had issues — check output above and tune system prompts")
    print(f"{'='*68}\n")


if __name__ == "__main__":
    main()
