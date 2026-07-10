"""
config.py — Single source of truth for all model names, thresholds,
            and Firestore collection names.

LLM_BACKEND controls which inference layer is used:
  "local"     → Ollama running on localhost (no API key needed)
  "fireworks" → Fireworks AI cloud (requires FIREWORKS_API_KEY)

Your teammate can plug in the Fireworks Routing Engine later by
flipping LLM_BACKEND=fireworks in .env — no agent code changes needed.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).parent.parent
load_dotenv(BASE_DIR / ".env")

# ── LLM Backend routing ───────────────────────────────────────────────────────
# Set to "local" (Ollama) or "fireworks" in .env
LLM_BACKEND: str = os.environ.get("LLM_BACKEND", "local")

# ── Ollama (local) ────────────────────────────────────────────────────────────
OLLAMA_URL: str = os.environ.get("OLLAMA_URL", "http://localhost:11434/api/chat")

# Local model — llama3.1:8b is already pulled.
# Swap to "llama3.2:3b" if resources are tight.
LOCAL_MODEL: str = os.environ.get("LOCAL_MODEL", "llama3.1:8b")

# ── Fireworks AI (cloud — wired in by teammate later) ─────────────────────────
# Only read from env when LLM_BACKEND=fireworks to avoid crashing locally.
FIREWORKS_API_KEY: str = os.environ.get("FIREWORKS_API_KEY", "")
FIREWORKS_BASE_URL = "https://api.fireworks.ai/inference/v1"
CHAT_URL = f"{FIREWORKS_BASE_URL}/chat/completions"
FIREWORKS_EMBED_URL = f"{FIREWORKS_BASE_URL}/embeddings"

AUTH_HEADERS = {
    "Authorization": f"Bearer {FIREWORKS_API_KEY}",
    "Content-Type": "application/json",
}

# Fireworks model names (used when LLM_BACKEND="fireworks")
GOAL_MODEL = "accounts/fireworks/models/llama-v3p1-8b-instruct"
PLAN_MODEL = "accounts/fireworks/models/llama-v3p1-70b-instruct"
EMBED_MODEL = "nomic-ai/nomic-embed-text-v1.5"

# ── Firebase ──────────────────────────────────────────────────────────────────
# Option A: path to service-account JSON (download from Firebase Console)
firebase_key_env = os.environ.get("FIREBASE_KEY_PATH", "firebase-key.json")
FIREBASE_KEY_PATH: str = str(BASE_DIR / firebase_key_env) if not os.path.isabs(firebase_key_env) else firebase_key_env

# Option B: project ID only (works with open Firestore rules / ADC)
FIREBASE_PROJECT_ID: str = os.environ.get("FIREBASE_PROJECT_ID", "amd-hackathon-c23d8")

# ── Cache settings ────────────────────────────────────────────────────────────
# Cosine similarity threshold for a semantic cache hit (0–1).
SEMANTIC_THRESHOLD: float = 0.92

# Max Firestore docs to pull for in-app semantic search.
CACHE_LOOKBACK_LIMIT: int = 100

# ── Firestore collection names ────────────────────────────────────────────────
GOAL_COLLECTION = "goal_cache"
PLAN_COLLECTION = "plan_cache"
RUNS_COLLECTION = "pipeline_runs"

# ── Validation limits ─────────────────────────────────────────────────────────
MAX_TASKS_PER_PLAN: int = 15

# ── LLM call defaults ─────────────────────────────────────────────────────────
DEFAULT_TEMPERATURE: float = 0.2
DEFAULT_MAX_RETRIES: int = 2
REQUEST_TIMEOUT_LOCAL: int = 120   # Ollama on CPU can be slow — give it 2 min
REQUEST_TIMEOUT_CLOUD: int = 20    # Fireworks cloud calls are fast
