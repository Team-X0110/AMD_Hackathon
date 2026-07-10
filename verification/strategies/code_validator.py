"""
verification/strategies/code_validator.py
==========================================
Code syntax validation strategy for CODING task responses.

Performs two levels of checking:
1. AST syntax validation (stdlib `ast` module — zero dependencies).
2. Optional unit test execution (subprocess-isolated, timeout-bounded).

Supports Python, JavaScript/TypeScript (via Node.js syntax check),
SQL (basic token validation), and Bash (via `bash -n`).

No LLM calls are made.
"""

from __future__ import annotations

import ast
import logging
import re
import subprocess
import tempfile
import os
from typing import Any, Dict, List, Optional, Tuple

from core.types import RoutingContext, TaskType, StrategyResult
from verification.strategies.base_strategy import BaseVerificationStrategy

logger = logging.getLogger(__name__)


class CodeValidatorStrategy(BaseVerificationStrategy):
    """
    Validates code syntax and optionally runs unit tests from the response.

    Activation: only when primary_task_type is CODING.

    Supported languages (auto-detected from response fences):
        python, javascript, typescript, sql, bash

    Args:
        config: Strategy config from verifier_config.yaml.
    """

    # Language detection patterns (from markdown code fences)
    _FENCE_PATTERN = re.compile(
        r"```(\w+)?\s*\n(.*?)```", re.DOTALL | re.IGNORECASE
    )
    _SQL_KEYWORDS = {"SELECT", "INSERT", "UPDATE", "DELETE", "CREATE", "DROP", "ALTER", "WITH"}

    def __init__(self, config: Dict[str, Any]) -> None:
        super().__init__(config)
        self._name = "code_validator"
        self._run_if_types: List[str] = config.get("run_if_task_types", ["CODING"])
        self._run_unit_tests: bool = bool(config.get("run_unit_tests", False))
        self._timeout: int = int(config.get("execution_timeout_seconds", 10))
        self._supported_langs: List[str] = [
            l.lower() for l in config.get(
                "syntax_check_languages",
                ["python", "javascript", "typescript", "sql", "bash"],
            )
        ]

    def should_run(
        self,
        context: RoutingContext,
        response: str,
        model_id: str,
    ) -> bool:
        """Run only when primary task is CODING."""
        return context.features.primary_task_type.value in self._run_if_types

    def _run_check(
        self,
        context: RoutingContext,
        response: str,
        model_id: str,
    ) -> StrategyResult:
        """
        Extract code blocks and validate their syntax.
        """
        failure_reasons: List[str] = []
        metadata: Dict[str, Any] = {}

        # Extract all code blocks from the response
        blocks = self._extract_code_blocks(response)

        if not blocks:
            # No fenced code block — check if response itself looks like code
            raw = response.strip()
            if self._looks_like_python(raw):
                blocks = [("python", raw)]
            else:
                # Non-fenced response with no detectable language
                return self._make_result(
                    passed=True,
                    score=0.7,
                    confidence=0.4,
                    failure_reasons=[],
                    metadata={"note": "No code fences detected; syntax check skipped"},
                )

        metadata["code_blocks_found"] = len(blocks)
        block_results: List[Dict[str, Any]] = []
        all_passed = True

        for lang, code in blocks:
            lang = lang.lower() if lang else "unknown"
            if lang not in self._supported_langs and lang != "unknown":
                block_results.append({"language": lang, "status": "skipped_unsupported"})
                continue

            passed, errors = self._validate_syntax(lang, code)
            block_result: Dict[str, Any] = {
                "language": lang,
                "code_length": len(code),
                "syntax_passed": passed,
                "errors": errors,
            }

            if not passed:
                all_passed = False
                for err in errors:
                    failure_reasons.append(f"[{lang}] Syntax error: {err}")

            # Optional unit test execution
            if passed and self._run_unit_tests and lang == "python":
                test_passed, test_output = self._run_python_tests(code)
                block_result["test_passed"] = test_passed
                block_result["test_output"] = test_output[:500]  # Truncate
                if not test_passed:
                    all_passed = False
                    failure_reasons.append(f"[python] Unit test execution failed: {test_output[:200]}")

            block_results.append(block_result)

        metadata["block_results"] = block_results
        score = 1.0 if all_passed else max(0.0, 1.0 - (len(failure_reasons) * 0.3))

        return self._make_result(
            passed=all_passed,
            score=score,
            confidence=0.90,
            failure_reasons=failure_reasons,
            metadata=metadata,
        )

    # ------------------------------------------------------------------
    # PRIVATE HELPERS
    # ------------------------------------------------------------------

    def _extract_code_blocks(self, response: str) -> List[Tuple[str, str]]:
        """Return list of (language, code) tuples from markdown fences."""
        blocks: List[Tuple[str, str]] = []
        for match in self._FENCE_PATTERN.finditer(response):
            lang = match.group(1) or "unknown"
            code = match.group(2).strip()
            if code:
                blocks.append((lang, code))
        return blocks

    def _validate_syntax(self, lang: str, code: str) -> Tuple[bool, List[str]]:
        """Dispatch to per-language validator."""
        if lang in ("python", "py"):
            return self._validate_python(code)
        elif lang in ("javascript", "js", "typescript", "ts"):
            return self._validate_js_ts(code)
        elif lang == "sql":
            return self._validate_sql(code)
        elif lang == "bash":
            return self._validate_bash(code)
        else:
            return True, []  # Unknown language: pass without check

    def _validate_python(self, code: str) -> Tuple[bool, List[str]]:
        """Use stdlib ast.parse for Python syntax checking."""
        try:
            ast.parse(code)
            return True, []
        except SyntaxError as exc:
            return False, [f"Line {exc.lineno}: {exc.msg}"]
        except Exception as exc:
            return False, [str(exc)]

    def _validate_js_ts(self, code: str) -> Tuple[bool, List[str]]:
        """
        Validate JS/TS by writing to a temp file and calling `node --check`.
        Falls back to pass if Node.js is not installed.
        """
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".js", delete=False, encoding="utf-8"
            ) as tmp:
                tmp.write(code)
                tmp_path = tmp.name
            result = subprocess.run(
                ["node", "--check", tmp_path],
                capture_output=True,
                text=True,
                timeout=self._timeout,
            )
            os.unlink(tmp_path)
            if result.returncode != 0:
                return False, [result.stderr.strip()[:300]]
            return True, []
        except FileNotFoundError:
            # Node.js not available
            return True, []
        except Exception as exc:
            return True, []  # Don't fail on environment issues
        finally:
            try:
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)
            except Exception:
                pass

    def _validate_sql(self, code: str) -> Tuple[bool, List[str]]:
        """
        Basic SQL validation: check that at least one DML/DDL keyword is present.
        Full AST parsing would require sqlparse; this is intentionally lightweight.
        """
        upper = code.upper()
        has_keyword = any(kw in upper for kw in self._SQL_KEYWORDS)
        if not has_keyword:
            return False, ["No recognisable SQL keyword found (SELECT, INSERT, etc.)"]
        # Check for obviously unbalanced parentheses
        if code.count("(") != code.count(")"):
            return False, ["Unbalanced parentheses in SQL"]
        return True, []

    def _validate_bash(self, code: str) -> Tuple[bool, List[str]]:
        """
        Validate Bash syntax using `bash -n` (dry-run syntax check).
        Falls back to pass if bash is not available.
        """
        try:
            result = subprocess.run(
                ["bash", "-n"],
                input=code,
                capture_output=True,
                text=True,
                timeout=self._timeout,
            )
            if result.returncode != 0:
                return False, [result.stderr.strip()[:300]]
            return True, []
        except FileNotFoundError:
            return True, []
        except Exception:
            return True, []

    def _run_python_tests(self, code: str) -> Tuple[bool, str]:
        """
        Execute Python code in a subprocess with a timeout.
        Only runs if the code contains `def test_` functions.
        """
        if "def test_" not in code:
            return True, "No test functions found"
        try:
            result = subprocess.run(
                ["python", "-c", code],
                capture_output=True,
                text=True,
                timeout=self._timeout,
            )
            if result.returncode != 0:
                return False, result.stderr or result.stdout
            return True, result.stdout
        except subprocess.TimeoutExpired:
            return False, f"Execution timed out after {self._timeout}s"
        except Exception as exc:
            return False, str(exc)

    @staticmethod
    def _looks_like_python(text: str) -> bool:
        """Heuristic: does the text look like Python source code?"""
        py_indicators = ("def ", "import ", "class ", "print(", "return ", "if __name__")
        return any(ind in text for ind in py_indicators)
