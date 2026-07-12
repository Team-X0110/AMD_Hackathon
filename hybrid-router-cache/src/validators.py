"""
validators.py — Schema + graph validation for both agents.
Raises ValueError with a descriptive message so the retry logic in
agents knows exactly what to append to the corrective prompt.
"""
from __future__ import annotations
from collections import deque

from pydantic import ValidationError

from src.schemas import (
    GoalSchema,
    GOAL_SCHEMA_KEYS, VALID_COMPLEXITY_HINTS,
    PlanSchema,
    PLAN_SCHEMA_KEYS, TASK_SCHEMA_KEYS, VALID_EFFORT_SIZES,
    RefinedPromptSchema,
    REFINEMENT_SCHEMA_KEYS,
)


# ── Goal Understanding ────────────────────────────────────────────────────────

def validate_goal_schema(goal: dict) -> None:
    """Raise ValueError if the goal dict is missing required keys or has bad values."""
    if not isinstance(goal, dict):
        raise ValueError(f"Expected dict, got {type(goal).__name__}")

    missing = GOAL_SCHEMA_KEYS - goal.keys()
    if missing:
        raise ValueError(f"Goal JSON missing required keys: {sorted(missing)}")

    if goal["complexity_hint"] not in VALID_COMPLEXITY_HINTS:
        raise ValueError(
            f"Invalid complexity_hint '{goal['complexity_hint']}'. "
            f"Must be one of: {sorted(VALID_COMPLEXITY_HINTS)}"
        )

    if not isinstance(goal.get("entities"), list):
        raise ValueError("'entities' must be a list")

    if not isinstance(goal.get("constraints"), list):
        raise ValueError("'constraints' must be a list")

    if not isinstance(goal.get("success_criteria"), list):
        raise ValueError("'success_criteria' must be a list")

    try:
        GoalSchema.model_validate(goal)
    except ValidationError as exc:
        raise ValueError(f"Invalid goal JSON: {exc}") from exc


# ── Task Planning ─────────────────────────────────────────────────────────────

def validate_task_graph(plan: dict, max_tasks: int = 15) -> None:
    """
    Validate the task plan dict:
      - Required top-level keys present
      - Each task has required fields
      - No unknown dependency IDs
      - No cycles in the dependency graph
      - Not too many tasks (LLMs occasionally over-decompose)
    """
    if not isinstance(plan, dict):
        raise ValueError(f"Expected dict, got {type(plan).__name__}")

    missing_top = PLAN_SCHEMA_KEYS - plan.keys()
    if missing_top:
        raise ValueError(f"Plan JSON missing top-level keys: {sorted(missing_top)}")

    tasks = plan["tasks"]
    if not isinstance(tasks, list) or len(tasks) == 0:
        raise ValueError("'tasks' must be a non-empty list")

    if len(tasks) > max_tasks:
        raise ValueError(
            f"Too many tasks ({len(tasks)}). Max is {max_tasks}. "
            "Consolidate related steps."
        )

    try:
        PlanSchema.model_validate(plan)
    except ValidationError as exc:
        raise ValueError(f"Invalid plan JSON: {exc}") from exc

    # Validate each task's fields
    ids: set[str] = set()
    for i, task in enumerate(tasks):
        missing_task = TASK_SCHEMA_KEYS - task.keys()
        if missing_task:
            raise ValueError(
                f"Task at index {i} missing keys: {sorted(missing_task)}"
            )
        if task["estimated_effort"] not in VALID_EFFORT_SIZES:
            raise ValueError(
                f"Task '{task['id']}' has invalid estimated_effort "
                f"'{task['estimated_effort']}'. Must be one of {sorted(VALID_EFFORT_SIZES)}"
            )
        ids.add(task["id"])

    # Check all dependency references resolve
    for task in tasks:
        for dep in task["depends_on"]:
            if dep not in ids:
                raise ValueError(
                    f"Unknown dependency '{dep}' in task '{task['id']}'. "
                    f"Known IDs: {sorted(ids)}"
                )

    # Cycle detection — Kahn's algorithm (topological sort)
    _check_no_cycles(tasks, ids)


def _check_no_cycles(tasks: list[dict], ids: set[str]) -> None:
    """Raise ValueError if the dependency graph has cycles (uses Kahn's algorithm)."""
    in_degree: dict[str, int] = {tid: 0 for tid in ids}
    adj: dict[str, list[str]] = {tid: [] for tid in ids}

    for task in tasks:
        for dep in task["depends_on"]:
            adj[dep].append(task["id"])
            in_degree[task["id"]] += 1

    queue = deque(tid for tid, deg in in_degree.items() if deg == 0)
    visited = 0

    while queue:
        node = queue.popleft()
        visited += 1
        for neighbour in adj[node]:
            in_degree[neighbour] -= 1
            if in_degree[neighbour] == 0:
                queue.append(neighbour)

    if visited != len(ids):
        raise ValueError(
            "Cycle detected in task dependency graph. "
            "Ensure no task directly or transitively depends on itself."
        )


# ── Prompt Refinement ─────────────────────────────────────────────────────────

def validate_refinement_schema(refinement: dict) -> None:
    """Raise ValueError if the refinement dict is missing required keys or has bad values."""
    if not isinstance(refinement, dict):
        raise ValueError(f"Expected dict, got {type(refinement).__name__}")

    missing = REFINEMENT_SCHEMA_KEYS - refinement.keys()
    if missing:
        raise ValueError(f"Refinement JSON missing required keys: {sorted(missing)}")

    if not isinstance(refinement.get("changes_made"), list):
        raise ValueError("'changes_made' must be a list")

    if not isinstance(refinement.get("ambiguity_resolved"), bool):
        raise ValueError("'ambiguity_resolved' must be a boolean")

    try:
        RefinedPromptSchema.model_validate(refinement)
    except ValidationError as exc:
        raise ValueError(f"Invalid refinement JSON: {exc}") from exc
