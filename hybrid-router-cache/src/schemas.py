"""
schemas.py — Expected JSON shapes for both agents.
Define keys once here; validators.py and agents import from here.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

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


class GoalSchema(BaseModel):
    """Validated output from the Goal Understanding agent."""

    model_config = ConfigDict(extra="allow")

    intent: str = Field(min_length=1)
    entities: list[str]
    constraints: list[str]
    success_criteria: list[str]
    domain: str = Field(min_length=1)
    complexity_hint: Literal["low", "medium", "high"]

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


class TaskSchema(BaseModel):
    """Validated task item emitted by the Task Planning agent."""

    model_config = ConfigDict(extra="allow")

    id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    description: str
    depends_on: list[str]
    estimated_effort: Literal["S", "M", "L", "XL"]


class PlanSchema(BaseModel):
    """Validated output from the Task Planning agent."""

    model_config = ConfigDict(extra="allow")

    tasks: list[TaskSchema] = Field(min_length=1)
    execution_order: list[str]
    parallel_groups: list[list[str]]

# ── Prompt Refinement Agent ───────────────────────────────────────────────────

REFINEMENT_SCHEMA_KEYS = frozenset({
    "refined_prompt",   # str — the polished, clear, and actionable prompt
    "ambiguity_resolved", # bool — whether ambiguity was resolved or assumed
    "changes_made",     # list — brief descriptions of changes made (can be empty)
})

class RefinedPromptSchema(BaseModel):
    """Validated output from the Prompt Refinement agent."""

    model_config = ConfigDict(extra="allow")

    refined_prompt: str = Field(min_length=1)
    ambiguity_resolved: bool
    changes_made: list[str]
