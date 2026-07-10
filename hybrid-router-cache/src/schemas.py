"""
schemas.py — Expected JSON shapes for both agents.
Define keys once here; validators.py and agents import from here.
"""

# ── Goal Understanding Agent ──────────────────────────────────────────────────
GOAL_SCHEMA_KEYS = frozenset({
    "intent",           # str  — short verb phrase of what the user wants to do
    "entities",         # list — key nouns (systems, technologies, actors)
    "constraints",      # list — requirements, limits, non-functional concerns
    "success_criteria", # list — measurable conditions for "done"
    "domain",           # str  — e.g. "software engineering", "data analysis"
    "complexity_hint",  # str  — one of: "low" | "medium" | "high"
})

VALID_COMPLEXITY_HINTS = frozenset({"low", "medium", "high"})

# ── Task Planning Agent ───────────────────────────────────────────────────────
# Expected top-level plan structure:
#   {
#     "tasks": [
#       {
#         "id": "t1",
#         "title": "...",
#         "description": "...",
#         "depends_on": [],       # list of task ids this task depends on
#         "estimated_effort": "S" # one of: S | M | L | XL
#       },
#       ...
#     ],
#     "execution_order": ["t1", "t2", ...],   # topological order suggestion
#     "parallel_groups": [["t2", "t3"], ...]  # tasks safe to run concurrently
#   }

PLAN_SCHEMA_KEYS = frozenset({"tasks", "execution_order", "parallel_groups"})

TASK_SCHEMA_KEYS = frozenset({
    "id",
    "title",
    "description",
    "depends_on",
    "estimated_effort",
})

VALID_EFFORT_SIZES = frozenset({"S", "M", "L", "XL"})
