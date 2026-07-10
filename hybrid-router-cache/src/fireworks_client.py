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
import time

import requests

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
    REQUEST_TIMEOUT_CLOUD,
    # Routing
    LLM_BACKEND,
    DEFAULT_TEMPERATURE,
    DEFAULT_MAX_RETRIES,
)


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

            # Ollama token counts
            usage = {
                "prompt_tokens": body.get("prompt_eval_count", 0),
                "completion_tokens": body.get("eval_count", 0),
                "total_tokens": (
                    body.get("prompt_eval_count", 0) + body.get("eval_count", 0)
                ),
            }
            return json.loads(content), usage

        except requests.exceptions.ConnectionError as e:
            raise RuntimeError(
                "Cannot connect to Ollama at http://localhost:11434. "
                "Make sure Ollama is running: `ollama serve`"
            ) from e

        except (requests.RequestException, json.JSONDecodeError, KeyError) as e:
            if attempt < max_retries:
                wait = 1.5 * (attempt + 1)
                print(f"[ollama] Error attempt {attempt + 1}: {e}, retrying in {wait:.1f}s")
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
            # Normalise keys to match Ollama shape
            return json.loads(content), {
                "prompt_tokens": usage.get("prompt_tokens", 0),
                "completion_tokens": usage.get("completion_tokens", 0),
                "total_tokens": usage.get("total_tokens", 0),
            }

        except requests.exceptions.HTTPError as e:
            status = e.response.status_code if e.response is not None else 0
            if status in (429, 500, 502, 503, 504) and attempt < max_retries:
                wait = 1.5 * (attempt + 1)
                print(f"[fireworks] HTTP {status} attempt {attempt + 1}, retrying in {wait:.1f}s")
                time.sleep(wait)
                last_exc = e
                continue
            raise RuntimeError(f"Fireworks HTTP {status}: {e}") from e

        except (requests.RequestException, json.JSONDecodeError, KeyError) as e:
            if attempt < max_retries:
                wait = 1.5 * (attempt + 1)
                print(f"[fireworks] Error attempt {attempt + 1}: {e}, retrying in {wait:.1f}s")
                time.sleep(wait)
                last_exc = e
                continue
            raise RuntimeError(
                f"Fireworks call failed after {max_retries + 1} attempts: {e}"
            ) from e

    raise RuntimeError(f"Fireworks call failed: {last_exc}")


# ─────────────────────────────────────────────────────────────────────────────
# Embeddings  (used by semantic cache)
# ─────────────────────────────────────────────────────────────────────────────

def get_embedding(
    text: str,
    model: str = EMBED_MODEL,
    max_retries: int = DEFAULT_MAX_RETRIES,
) -> list[float]:
    """
    Get a text embedding vector.
    Uses local Ollama if LLM_BACKEND is "local", otherwise Fireworks cloud.
    """
    if LLM_BACKEND == "local":
        OLLAMA_EMBED_URL = "http://localhost:11434/api/embeddings"
        payload = {"model": "nomic-embed-text", "prompt": text}
        for attempt in range(max_retries + 1):
            try:
                resp = requests.post(OLLAMA_EMBED_URL, json=payload, timeout=REQUEST_TIMEOUT_LOCAL)
                resp.raise_for_status()
                return resp.json()["embedding"]
            except (requests.RequestException, KeyError) as e:
                if attempt < max_retries:
                    time.sleep(1.5 * (attempt + 1))
                    continue
                raise RuntimeError(f"Ollama embedding failed: {e}") from e

    # Fireworks Cloud
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
                print(f"[embedding] Error attempt {attempt + 1}: {e}, retrying in {wait:.1f}s")
                time.sleep(wait)
                last_exc = e
                continue
            raise RuntimeError(
                f"Embedding call failed after {max_retries + 1} attempts: {e}"
            ) from e

    raise RuntimeError(f"Embedding call failed: {last_exc}")


