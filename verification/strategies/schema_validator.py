"""
verification/strategies/schema_validator.py
============================================
JSON / Pydantic schema validation strategy.

Checks that the model response is valid JSON and, when a schema is
provided in the routing context metadata, validates the parsed object
against that schema using jsonschema.

No LLM calls are made — pure structural validation.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from core.types import RoutingContext, StrategyResult
from verification.strategies.base_strategy import BaseVerificationStrategy

logger = logging.getLogger(__name__)

try:
    import jsonschema
    _JSONSCHEMA_AVAILABLE = True
except ImportError:
    _JSONSCHEMA_AVAILABLE = False
    logger.warning("jsonschema not installed — schema_validator will skip schema checks")


class SchemaValidatorStrategy(BaseVerificationStrategy):
    """
    Validates that the response is valid JSON and matches an optional schema.

    Activation condition (from verifier_config.yaml):
        run_if_formats: ["json", "structured", "pydantic"]

    Schema source (priority order):
        1. context.metadata["expected_schema"]  — jsonschema dict
        2. context.metadata["pydantic_model"]   — Pydantic model class (type)
        3. No schema: only JSON parsability is checked.

    Args:
        config: Strategy config from verifier_config.yaml.
    """

    def __init__(self, config: Dict[str, Any]) -> None:
        super().__init__(config)
        self._name = "schema_validator"
        self._run_if_formats: List[str] = config.get(
            "run_if_formats", ["json", "structured", "pydantic"]
        )
        self._strict_mode: bool = bool(config.get("strict_mode", True))

    def should_run(
        self,
        context: RoutingContext,
        response: str,
        model_id: str,
    ) -> bool:
        """Run only when the expected output format demands structured/JSON output."""
        return context.features.expected_output_format in self._run_if_formats

    def _run_check(
        self,
        context: RoutingContext,
        response: str,
        model_id: str,
    ) -> StrategyResult:
        """
        Parse the response as JSON and optionally validate against a schema.
        """
        failure_reasons: List[str] = []
        metadata: Dict[str, Any] = {}

        # Step 1: Extract JSON from response (handle markdown code fences)
        json_str = self._extract_json(response)
        metadata["extracted_json_length"] = len(json_str)

        # Step 2: Parse JSON
        parsed: Optional[Any] = None
        try:
            parsed = json.loads(json_str)
            metadata["json_valid"] = True
            metadata["parsed_type"] = type(parsed).__name__
        except json.JSONDecodeError as exc:
            metadata["json_valid"] = False
            metadata["json_error"] = str(exc)
            failure_reasons.append(f"Response is not valid JSON: {exc}")
            return self._make_result(
                passed=False,
                score=0.0,
                confidence=0.95,  # High confidence this is a real failure
                failure_reasons=failure_reasons,
                metadata=metadata,
            )

        # Step 3: Schema validation (if schema provided)
        schema: Optional[Dict[str, Any]] = context.metadata.get("expected_schema")
        pydantic_model = context.metadata.get("pydantic_model")

        if schema and _JSONSCHEMA_AVAILABLE:
            schema_errors = self._validate_jsonschema(parsed, schema, metadata)
            failure_reasons.extend(schema_errors)
        elif pydantic_model is not None:
            pydantic_errors = self._validate_pydantic(parsed, pydantic_model, metadata)
            failure_reasons.extend(pydantic_errors)

        passed = len(failure_reasons) == 0
        score = 1.0 if passed else max(0.0, 1.0 - (len(failure_reasons) * 0.25))

        return self._make_result(
            passed=passed,
            score=score,
            confidence=0.95,
            failure_reasons=failure_reasons,
            metadata=metadata,
        )

    # ------------------------------------------------------------------
    # PRIVATE HELPERS
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_json(response: str) -> str:
        """
        Extract JSON from a response that may be wrapped in markdown code fences.
        Falls back to stripping leading/trailing whitespace.
        """
        stripped = response.strip()
        # Handle ```json ... ``` or ``` ... ``` fences
        for fence in ("```json", "```JSON", "```"):
            if stripped.startswith(fence):
                stripped = stripped[len(fence):]
                if stripped.endswith("```"):
                    stripped = stripped[:-3]
                return stripped.strip()
        return stripped

    def _validate_jsonschema(
        self,
        parsed: Any,
        schema: Dict[str, Any],
        metadata: Dict[str, Any],
    ) -> List[str]:
        """Validate parsed JSON against a jsonschema dict."""
        errors: List[str] = []
        try:
            validator = jsonschema.Draft7Validator(schema)
            validation_errors = list(validator.iter_errors(parsed))
            metadata["schema_validation_errors"] = len(validation_errors)
            if self._strict_mode:
                for err in validation_errors:
                    errors.append(f"Schema violation: {err.message} at {list(err.path)}")
            elif validation_errors:
                errors.append(
                    f"{len(validation_errors)} schema violation(s): "
                    f"{validation_errors[0].message}"
                )
        except Exception as exc:
            errors.append(f"Schema validation error: {exc}")
        return errors

    def _validate_pydantic(
        self,
        parsed: Any,
        pydantic_model: Any,
        metadata: Dict[str, Any],
    ) -> List[str]:
        """Validate parsed JSON using a Pydantic model class."""
        errors: List[str] = []
        try:
            pydantic_model(**parsed) if isinstance(parsed, dict) else pydantic_model(parsed)
            metadata["pydantic_valid"] = True
        except Exception as exc:
            metadata["pydantic_valid"] = False
            errors.append(f"Pydantic validation failed: {exc}")
        return errors
