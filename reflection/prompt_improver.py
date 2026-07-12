"""
reflection/prompt_improver.py
==============================
Automatically rewrites prompts before a retry attempt.

The improver reads prompt templates from reflection_config.yaml and
applies them based on the ReflectionAction that was chosen.

Key design decisions:
- The original RoutingContext is NEVER mutated.
- Returns a new RoutingContext with improved original_messages.
- Improvements are minimal and targeted — avoid bloating the prompt,
  which would waste tokens.
- For token efficiency: improvements are prepended/appended as system
  messages rather than rewriting the full user message.
"""

from __future__ import annotations

import copy
import json
import logging
from typing import Any, Dict, List, Optional

import yaml

from core.interfaces import IPromptImprover
from core.types import (
    ConfidenceEngineResult,
    RoutingContext,
    ReflectionAction,
)

logger = logging.getLogger(__name__)


class PromptImprover(IPromptImprover):
    """
    Applies targeted prompt improvements based on the reflection action.

    Args:
        reflection_config_path: Path to config/reflection_config.yaml.
    """

    def __init__(self, reflection_config_path: str) -> None:
        with open(reflection_config_path, "r", encoding="utf-8") as fh:
            cfg = yaml.safe_load(fh)
        self._templates: Dict[str, str] = cfg.get("prompt_improvement", {})

    # ------------------------------------------------------------------
    # IPromptImprover implementation
    # ------------------------------------------------------------------

    def improve(
        self,
        context: RoutingContext,
        action: ReflectionAction,
        attempt_number: int,
        failure_reasons: List[str],
    ) -> RoutingContext:
        """
        Return a new RoutingContext with an improved prompt for retry.

        The improvement strategy depends on the action:
            RETRY_SAME_COT       → prepend chain-of-thought prefix to system message
            RETRY_SAME_GROUNDING → prepend grounding/factuality prefix
            RETRY_SAME_FORMAT    → append format clarification to last user message
            RETRY_SAME_SCHEMA    → inject schema example into system message
            RETRY_WITH_CONTEXT   → inject additional_context into messages
            RETRY_TOOL_SIMPLIFY  → append tool simplification hint
            RETRY_CODING_MODEL   → no prompt change (model switch handles it)
            ESCALATE             → no prompt change (model switch handles it)

        Args:
            context: Original routing context (not mutated).
            action: Reflection action driving this improvement.
            attempt_number: Current retry count (1-indexed).
            failure_reasons: Failure reasons from the last verification.

        Returns:
            New RoutingContext with improved messages.
        """
        # Deep copy messages to avoid mutation
        new_messages: List[Dict[str, Any]] = copy.deepcopy(context.original_messages)
        improvement_applied = False
        improvement_type: Optional[str] = None

        if action == ReflectionAction.RETRY_SAME_COT:
            new_messages = self._prepend_system(
                new_messages,
                self._templates.get("cot_prefix", "Think step by step.\n"),
            )
            improvement_applied = True
            improvement_type = "cot_prefix"

        elif action == ReflectionAction.RETRY_SAME_GROUNDING:
            new_messages = self._prepend_system(
                new_messages,
                self._templates.get("grounding_prefix", "Answer only from known facts.\n"),
            )
            improvement_applied = True
            improvement_type = "grounding_prefix"

        elif action == ReflectionAction.RETRY_SAME_FORMAT:
            suffix = self._templates.get("format_clarification_suffix", "")
            if suffix:
                new_messages = self._append_to_last_user(new_messages, f"\n\n{suffix}")
                improvement_applied = True
                improvement_type = "format_clarification"

        elif action == ReflectionAction.RETRY_SAME_SCHEMA:
            schema = context.metadata.get("expected_schema")
            schema_example = context.metadata.get("schema_example", "{}")
            if schema:
                template = self._templates.get("schema_example_prefix", "")
                injection = template.format(
                    schema_json=json.dumps(schema, indent=2),
                    schema_example=json.dumps(schema_example, indent=2),
                )
                new_messages = self._prepend_system(new_messages, injection)
                improvement_applied = True
                improvement_type = "schema_injection"

        elif action == ReflectionAction.RETRY_WITH_CONTEXT:
            extra_ctx = context.additional_context or self._build_failure_context(
                failure_reasons
            )
            template = self._templates.get(
                "context_injection_template",
                "Additional context:\n{additional_context}\n",
            )
            injection = template.format(additional_context=extra_ctx)
            new_messages = self._prepend_system(new_messages, injection)
            improvement_applied = True
            improvement_type = "context_injection"

        elif action == ReflectionAction.RETRY_TOOL_SIMPLIFY:
            suffix = self._templates.get("tool_simplification_suffix", "")
            if suffix:
                new_messages = self._append_to_last_user(new_messages, f"\n\n{suffix}")
                improvement_applied = True
                improvement_type = "tool_simplification"

        # For ESCALATE / RETRY_CODING_MODEL / ABORT: no prompt changes
        # The routing engine or reflection agent handles model switching

        # Add a token budget hint on later attempts to encourage conciseness
        if attempt_number >= 2:
            max_tokens = context.complexity.estimated_output_tokens
            budget_hint = self._templates.get(
                "token_budget_instruction", ""
            ).format(max_tokens=max_tokens)
            if budget_hint:
                new_messages = self._append_to_last_user(
                    new_messages, f"\n{budget_hint}"
                )

        if improvement_applied:
            logger.debug(
                "prompt_improved",
                extra={
                    "request_id": context.request_id,
                    "action": action.value,
                    "improvement_type": improvement_type,
                    "attempt_number": attempt_number,
                },
            )

        # Build new context (shallow copy, replace messages)
        return RoutingContext(
            request_id=context.request_id,
            features=context.features,
            complexity=context.complexity,
            confidence=context.confidence,
            original_messages=new_messages,
            additional_context=context.additional_context,
            metadata={
                **context.metadata,
                "improvement_applied": improvement_applied,
                "improvement_type": improvement_type,
                "attempt_number": attempt_number,
            },
        )

    # ------------------------------------------------------------------
    # PRIVATE HELPERS
    # ------------------------------------------------------------------

    @staticmethod
    def _prepend_system(
        messages: List[Dict[str, Any]],
        content: str,
    ) -> List[Dict[str, Any]]:
        """
        Prepend content to the first system message, or insert a new system
        message at the beginning if none exists.
        """
        if not content.strip():
            return messages

        if messages and messages[0].get("role") == "system":
            existing = messages[0].get("content", "")
            messages[0] = {"role": "system", "content": content + "\n\n" + existing}
        else:
            messages.insert(0, {"role": "system", "content": content.strip()})

        return messages

    @staticmethod
    def _append_to_last_user(
        messages: List[Dict[str, Any]],
        content: str,
    ) -> List[Dict[str, Any]]:
        """
        Append content to the last user message.
        If no user message exists, append a new user message.
        """
        if not content.strip():
            return messages

        for i in range(len(messages) - 1, -1, -1):
            if messages[i].get("role") == "user":
                existing = messages[i].get("content", "")
                if isinstance(existing, str):
                    messages[i] = {"role": "user", "content": existing + content}
                elif isinstance(existing, list):
                    # Multimodal content list
                    existing.append({"type": "text", "text": content})
                    messages[i] = {"role": "user", "content": existing}
                return messages

        # No user message found — append one
        messages.append({"role": "user", "content": content.strip()})
        return messages

    @staticmethod
    def _build_failure_context(failure_reasons: List[str]) -> str:
        """Build a concise failure summary to inject as additional context."""
        if not failure_reasons:
            return "The previous response did not fully satisfy the requirements."
        lines = "\n".join(f"- {r}" for r in failure_reasons[:5])
        return f"The previous attempt had the following issues:\n{lines}\nPlease address these in your response."
