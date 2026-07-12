"""
fireworks_client.py — Unified LLM client with local (Ollama) and cloud (Fireworks) backends.

Public API used by agents:
    call_llm(tier, model, system_prompt, user_prompt) -> (dict, usage_dict)

Tiers:
    "local"     -> call_ollama_chat  (llama3.1:8b on localhost:11434, no API key)
    "fireworks" -> call_fireworks_chat (Fireworks AI cloud, requires FIREWORKS_API_KEY)

Both return the same shape: (parsed_json_dict, usage_dict)
  usage = {"prompt_tokens": int, "completion_tokens": int, "total_tokens": int}

Your teammate's Fireworks Routing Engine plugs in by changing LLM_BACKEND in .env
— zero agent code changes needed.
"""
from __future__ import annotations
import json
import logging
import time

import requests
import re

from src.config import (
    # Ollama
    OLLAMA_URL,
    LOCAL_MODEL,
    REQUEST_TIMEOUT_LOCAL,
    # Fireworks
    AUTH_HEADERS,
    CHAT_URL,
    FIREWORKS_EMBED_URL,
    EMBED_MODEL,
    EMBED_BACKEND,
    REQUEST_TIMEOUT_CLOUD,
    FIREWORKS_API_KEY,
    # Routing
    LLM_BACKEND,
    DEFAULT_TEMPERATURE,
    DEFAULT_MAX_RETRIES,
)

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Router  —  single call site for all agents
# ─────────────────────────────────────────────────────────────────────────────

def call_llm(
    tier: str,
    model: str,
    system_prompt: str,
    user_prompt: str,
    temperature: float = DEFAULT_TEMPERATURE,
    max_retries: int = DEFAULT_MAX_RETRIES,
) -> tuple[dict, dict]:
    """
    Route a chat call to the right backend.

    Args:
        tier:  "local" (Ollama) or "fireworks" (cloud). Pass LLM_BACKEND from config
               to always follow the .env setting.
        model: model identifier matching the tier (LOCAL_MODEL or GOAL_MODEL/PLAN_MODEL).

    Returns:
        (parsed_response: dict, usage: dict)
    """
    if tier == "local":
        return call_ollama_chat(model, system_prompt, user_prompt, temperature, max_retries)
    elif tier == "fireworks":
        return call_fireworks_chat(model, system_prompt, user_prompt, temperature, max_retries)
    else:
        raise ValueError(f"Unknown LLM tier '{tier}'. Use 'local' or 'fireworks'.")

# automatic schema repair
def _repair_goal_schema(data: dict) -> dict:
    """Ensure required GoalSchema fields always exist."""

    data.setdefault("intent", "")
    data.setdefault("entities", [])
    data.setdefault("constraints", [])
    data.setdefault("success_criteria", [])
    data.setdefault("domain", "general")
    data.setdefault("complexity_hint", "medium")

    return data

# ─────────────────────────────────────────────────────────────────────────────
# Ollama  (local)
# ─────────────────────────────────────────────────────────────────────────────

def call_ollama_chat(
    model: str,
    system_prompt: str,
    user_prompt: str,
    temperature: float = DEFAULT_TEMPERATURE,
    max_retries: int = DEFAULT_MAX_RETRIES,
) -> tuple[dict, dict]:
    """
    Call a local Ollama model via its REST API.

    Ollama exposes an OpenAI-compatible endpoint. Using "format": "json"
    forces JSON output — equivalent to Fireworks' response_format.

    Timeout is generous (120s) because CPU inference can be slow.
    """
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "stream": False,
        "format": "json",
        "options": {"temperature": temperature},
    }

    last_exc: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            resp = requests.post(
                OLLAMA_URL,
                json=payload,
                timeout=REQUEST_TIMEOUT_LOCAL,
            )
            resp.raise_for_status()

            body = resp.json()
            content = body["message"]["content"]
            parsed = json.loads(content)

            if isinstance(parsed, dict):
                parsed = _repair_goal_schema(parsed)

            return parsed, _normalize_usage(
                {
                    "prompt_tokens": body.get("prompt_eval_count", 0),
                    "completion_tokens": body.get("eval_count", 0),
                    "total_tokens": (
                        body.get("prompt_eval_count", 0) + body.get("eval_count", 0)
                    ),
                },
                backend="local",
            )

        except requests.exceptions.ConnectionError as e:
            raise RuntimeError(
                "Cannot connect to Ollama at http://localhost:11434. "
                "Make sure Ollama is running: `ollama serve`"
            ) from e

        except (requests.RequestException, json.JSONDecodeError, KeyError) as e:
            if attempt < max_retries:
                wait = 1.5 * (attempt + 1)
                logger.warning(
                    "Ollama error attempt %s: %s, retrying in %.1fs",
                    attempt + 1,
                    e,
                    wait,
                )
                time.sleep(wait)
                last_exc = e
                continue
            raise RuntimeError(
                f"Ollama call failed after {max_retries + 1} attempts: {e}"
            ) from e

    raise RuntimeError(f"Ollama call failed: {last_exc}")


# ─────────────────────────────────────────────────────────────────────────────
# Fireworks AI  (cloud — teammate plugs this in later)
# ─────────────────────────────────────────────────────────────────────────────

def call_fireworks_chat(
    model: str,
    system_prompt: str,
    user_prompt: str,
    temperature: float = DEFAULT_TEMPERATURE,
    max_retries: int = DEFAULT_MAX_RETRIES,
) -> tuple[dict, dict]:
    """
    Call Fireworks AI chat completions in JSON mode.
    Requires FIREWORKS_API_KEY in .env.
    """
    _require_fireworks_api_key()
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": temperature,
        "response_format": {"type": "json_object"},
    }

    last_exc: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            resp = requests.post(
                CHAT_URL,
                headers=AUTH_HEADERS,
                json=payload,
                timeout=REQUEST_TIMEOUT_CLOUD,
            )
            resp.raise_for_status()

            body = resp.json()
            content = body["choices"][0]["message"]["content"]
            usage = body.get("usage", {})

            parsed = json.loads(content)

            if isinstance(parsed, dict):
                parsed = _repair_goal_schema(parsed)

            return parsed, _normalize_usage(usage, backend="fireworks")

        except requests.exceptions.HTTPError as e:
            status = e.response.status_code if e.response is not None else 0
            if status in (429, 500, 502, 503, 504) and attempt < max_retries:
                wait = 1.5 * (attempt + 1)
                logger.warning(
                    "Fireworks HTTP %s attempt %s, retrying in %.1fs",
                    status,
                    attempt + 1,
                    wait,
                )
                time.sleep(wait)
                last_exc = e
                continue
            raise RuntimeError(f"Fireworks HTTP {status}: {e}") from e

        except (requests.RequestException, json.JSONDecodeError, KeyError) as e:
            if attempt < max_retries:
                wait = 1.5 * (attempt + 1)
                logger.warning(
                    "Fireworks error attempt %s: %s, retrying in %.1fs",
                    attempt + 1,
                    e,
                    wait,
                )
                time.sleep(wait)
                last_exc = e
                continue
            raise RuntimeError(
                f"Fireworks call failed after {max_retries + 1} attempts: {e}"
            ) from e

    raise RuntimeError(f"Fireworks call failed: {last_exc}")


def _normalize_usage(usage: dict, *, backend: str) -> dict:
    """Attach backend label so callers can split Fireworks vs local token counts."""
    normalized = {
        "prompt_tokens": usage.get("prompt_tokens", 0),
        "completion_tokens": usage.get("completion_tokens", 0),
        "total_tokens": usage.get("total_tokens", 0),
        "backend": backend,
    }
    if not normalized["total_tokens"]:
        normalized["total_tokens"] = (
            normalized["prompt_tokens"] + normalized["completion_tokens"]
        )
    return normalized


def _require_fireworks_api_key() -> None:
    if not FIREWORKS_API_KEY:
        raise RuntimeError("Missing FIREWORKS_API_KEY for Fireworks request")


def call_fireworks_with_tools(
    model: str,
    messages: list[dict],
    tools: list[dict],
    *,
    tool_choice: dict | str = "auto",
    temperature: float = 0.1,
    max_retries: int = DEFAULT_MAX_RETRIES,
) -> tuple[dict, dict]:
    """
    Fireworks Function Calling — returns parsed tool arguments and usage.

    Returns:
        (tool_args_dict, usage_dict with backend='fireworks')
    """
    _require_fireworks_api_key()
    payload: dict = {
        "model": model,
        "messages": messages,
        "tools": tools,
        "temperature": temperature,
    }
    if tool_choice != "auto":
        payload["tool_choice"] = tool_choice

    last_exc: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            resp = requests.post(
                CHAT_URL,
                headers=AUTH_HEADERS,
                json=payload,
                timeout=REQUEST_TIMEOUT_CLOUD,
            )
            resp.raise_for_status()

            body = resp.json()
            message = body["choices"][0]["message"]
            tool_calls = message.get("tool_calls") or []
            if not tool_calls:
                raise RuntimeError("Fireworks FC returned no tool_calls")

            raw_args = tool_calls[0]["function"]["arguments"]
            tool_args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
            if not isinstance(tool_args, dict):
                raise RuntimeError("Fireworks FC returned non-object tool arguments")
            usage = _normalize_usage(body.get("usage", {}), backend="fireworks")
            return tool_args, usage

        except requests.exceptions.HTTPError as e:
            status = e.response.status_code if e.response is not None else 0
            if status in (429, 500, 502, 503, 504) and attempt < max_retries:
                time.sleep(1.5 * (attempt + 1))
                last_exc = e
                continue
            raise RuntimeError(f"Fireworks FC HTTP {status}: {e}") from e

        except (requests.RequestException, json.JSONDecodeError, KeyError, IndexError) as e:
            if attempt < max_retries:
                time.sleep(1.5 * (attempt + 1))
                last_exc = e
                continue
            raise RuntimeError(f"Fireworks FC failed: {e}") from e

    raise RuntimeError(f"Fireworks FC failed: {last_exc}")


# ─────────────────────────────────────────────────────────────────────────────
# Embeddings  (used by semantic cache)
# ─────────────────────────────────────────────────────────────────────────────

def _get_embedding_local(text: str, max_retries: int) -> list[float]:
    ollama_embed_url = "http://localhost:11434/api/embeddings"
    payload = {"model": "nomic-embed-text", "prompt": text}
    last_exc: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            resp = requests.post(
                ollama_embed_url, json=payload, timeout=REQUEST_TIMEOUT_LOCAL
            )
            resp.raise_for_status()
            return resp.json()["embedding"]
        except requests.exceptions.ConnectionError as e:
            raise RuntimeError(
                "Cannot connect to Ollama at http://localhost:11434. "
                "Make sure Ollama is running: `ollama serve`"
            ) from e
        except (requests.RequestException, KeyError) as e:
            if attempt < max_retries:
                time.sleep(1.5 * (attempt + 1))
                last_exc = e
                continue
            raise RuntimeError(f"Ollama embedding failed: {e}") from e
    raise RuntimeError(f"Ollama embedding failed: {last_exc}")


def _get_embedding_fireworks(
    text: str,
    model: str,
    max_retries: int,
) -> list[float]:
    _require_fireworks_api_key()
    payload = {"model": model, "input": text}
    last_exc: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            resp = requests.post(
                FIREWORKS_EMBED_URL,
                headers=AUTH_HEADERS,
                json=payload,
                timeout=REQUEST_TIMEOUT_CLOUD,
            )
            resp.raise_for_status()
            return resp.json()["data"][0]["embedding"]

        except (requests.RequestException, KeyError, IndexError) as e:
            if attempt < max_retries:
                wait = 1.5 * (attempt + 1)
                logger.warning(
                    "Fireworks embedding error attempt %s: %s, retrying in %.1fs",
                    attempt + 1,
                    e,
                    wait,
                )
                time.sleep(wait)
                last_exc = e
                continue
            raise RuntimeError(
                f"Fireworks embedding failed after {max_retries + 1} attempts: {e}"
            ) from e

    raise RuntimeError(f"Fireworks embedding failed: {last_exc}")


def get_embedding(
    text: str,
    model: str = EMBED_MODEL,
    max_retries: int = DEFAULT_MAX_RETRIES,
) -> list[float]:
    """
    Get a text embedding vector.
    Prefers Fireworks when API key is available (cloud-backed).
    Falls back to local Ollama only if Fireworks is unavailable.
    """
    if FIREWORKS_API_KEY:
        return _get_embedding_fireworks(text, model, max_retries)
    
    if EMBED_BACKEND == "local":
        return _get_embedding_local(text, max_retries)
    
    raise RuntimeError("No embedding backend available: set FIREWORKS_API_KEY or EMBED_BACKEND=local")

def _extract_json(text: str) -> dict:
    text = text.strip()

    try: 
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{.*\}", text, re.DOTALL)

    if match:
        return json.loads(match.group(0))
    
    raise ValueError("No valid JSON found in model response.")
