# Hybrid Router Cache (Llama 3 Edition)

A two-agent LLM pipeline (Goal Understanding → Task Planning) with a two-layer cache:

- **Exact cache** — SHA-256 hash match on normalized prompt → zero tokens used
- **Semantic cache** — cosine similarity on embeddings → zero tokens, handles paraphrases

## Stack

| Component | Choice |
|-----------|--------|
| LLM Inference | Llama 3.1 8B (via Ollama locally or Fireworks AI) |
| Embeddings | nomic-ai/nomic-embed-text-v1.5 (via Fireworks) |
| Cache / DB | Google Firestore (Native mode) |
| Language | Python 3.11+ |

## Quick Start for Teammates

**Important**: Ask Swayam for the `firebase-key.json` file and the API keys, as they are not committed to git!

```bash
# 1. Install deps
pip install -r requirements.txt

# 2. Add API keys
cp .env.example .env   # then fill in FIREWORKS_API_KEY
# Place the Firebase service-account JSON in this directory and update FIREBASE_KEY_PATH in .env


# 3. Checkpoint 1 — confirm Firestore connection
python -c "from src.cache.firestore_client import get_db; db=get_db(); print('Firestore OK')"

# 4. Run full pipeline
python -c "
from src.pipeline import run_pipeline
import json
result = run_pipeline('Build a REST API for a todo app with user authentication')
print(json.dumps(result, indent=2))
"
```

## Project Layout

```
hybrid-router-cache/
├── .env                     # API keys (never commit)
├── requirements.txt
├── firebase-key.json        # Firebase service account (never commit)
├── src/
│   ├── config.py            # All model names, thresholds, collection names
│   ├── fireworks_client.py  # Retry-wrapped Fireworks API calls
│   ├── schemas.py           # Expected JSON shapes for both agents
│   ├── validators.py        # Schema + graph validation
│   ├── pipeline.py          # Orchestrates goal → plan, logs runs
│   ├── cache/
│   │   ├── firestore_client.py  # Singleton Firestore init
│   │   ├── exact_cache.py       # SHA-256 hash cache (read/write)
│   │   └── semantic_cache.py    # Embedding + cosine similarity lookup
│   └── agents/
│       ├── goal_understanding.py  # Goal Understanding Agent
│       └── task_planning.py       # Task Planning Agent
├── tests/
│   ├── test_cache.py
│   ├── test_goal_agent.py
│   ├── test_planning_agent.py
│   └── test_pipeline.py
└── logs/
    └── run_logs.jsonl       # Local structured log mirror
```

## Chat Worker Integration (Frontend-Backend Bridge)

To connect the Vite+React frontend chat app to the backend AI pipeline, we have a chat worker daemon. This worker listens to Firebase Realtime Database for new messages and responds automatically.

```bash
# To start the chat worker daemon
python src/chat_worker.py
```
Leave this running in a terminal. When you use the frontend to chat, the worker will pick up messages and reply with the generated pipeline plan.

## Cache Architecture

```
User Prompt
    │
    ▼
[Exact Cache] ──hit──► return cached goal/plan (0 tokens)
    │ miss
    ▼
[Semantic Cache] ──hit (score ≥ 0.92)──► return closest match (0 tokens)
    │ miss
    ▼
[Fireworks LLM call] ──► validate ──► store with embedding
```

## Known Limitations

- **Semantic search is O(N)**: pulls last `CACHE_LOOKBACK_LIMIT` docs and computes cosine similarity in-app.
  Fine for hackathon scale (hundreds to low-thousands of entries). For production, use Firestore's
  vector search extension or a dedicated vector DB (Pinecone, Weaviate).
- **Embedding cost**: every cache miss costs one chat call + one embedding call. Token counters
  track both separately.
- **Similarity threshold (0.92)** is a starting point — tune by plotting score distributions across
  near-duplicate and clearly-different prompts.

## Demo Sequence (Checkpoint 5)

```bash
python demo.py
```

Runs four prompts in sequence:
1. Fresh unique prompt → `cache_hit: none`, tokens > 0
2. Same prompt again → `cache_hit: exact`, tokens = 0
3. Reworded version → `cache_hit: semantic(0.9x)`, tokens = 0
4. Unrelated prompt → `cache_hit: none`, tokens > 0


Hybrid Router Cache (Llama & DeepSeek Edition)
A fully autonomous, multi-tier LLM orchestration engine (Goal Understanding → Task Planning) featuring a zero-latency FAISS vector cache and dynamic complexity routing.
🚀 Recent Architecture Upgrades
Local FAISS Semantic Cache (Task 3.1): Upgraded from O(N) database lookups to a highly efficient local FAISS vector index synced from Firebase, achieving true O(1) zero-token cache hits.
Feature Extraction (Task 3.2): Added pure Python static analysis to detect code blocks, JSON requirements, length constraints, and query domains before inference.
Complexity Estimator (Task 3.3): System mathematically evaluates prompt complexity on a 1-10 scale based on extracted features.
Dynamic Routing Engine (Task 3.4): System defaults to local execution (Ollama) for zero-cost operation and dynamically cloud-bursts to DeepSeek-V4-Pro for highly complex architectural tasks.
Hardened Execution: Upgraded cloud timeouts to 90s for massive JSON payload generation and optimized Firebase telemetry logging.
Stack
Component	Choice
LLM Inference (Local Tier)	Llama 3.1 8B (via local Ollama)
LLM Inference (Cloud Tier)	DeepSeek-V4-Pro (via Fireworks AI Serverless)
Semantic Cache	FAISS Local Vector Index
Embeddings	all-MiniLM-L6-v2 (Local) / nomic-embed-text-v1.5
Database / Telemetry	Firebase Realtime Database
Language	Python 3.11+
Quick Start for Teammates
Important: API keys and service accounts are deliberately excluded via .gitignore. Request amd-hackathon-*.json and the .env values from the team lead.
Bash
# 1. Install deps
pip install -r requirements.txt

# 2. Add API keys
cp .env.example .env   # then fill in FIREWORKS_API_KEY
# Place the Firebase service-account JSON in this directory and update FIREBASE_KEY_PATH in .env

# 3. Checkpoint 1 — Run the Cloud Diagnostics
python test_fireworks.py
python list_models.py

# 4. Start the Chat Daemon (Starts FAISS index and listens for frontend)
python src/chat_worker.py
Hybrid Routing Architecture
Plaintext
User Prompt
    │
    ▼
[FAISS Semantic Cache] ──hit (score ≥ 0.92)──► return cached JSON (0 tokens)
    │ miss
    ▼
[Feature Extractor] ──► calculates length, domain, formatting needs
    │
    ▼
[Routing Engine] ──► calculates complexity (1-10)
    │
    ├─► [LOCAL TIER]  (Complexity < 4) ──► Ollama (Llama 3.1 8B)
    │
    └─► [CLOUD TIER]  (Complexity ≥ 4) ──► Fireworks (DeepSeek-V4-Pro)
    │
    ▼
[Agent Pipeline] ──► executes Goal & Plan ──► stores to FAISS & Firebase
Project Layout
Plaintext
hybrid-router-cache/
├── .env                     # API keys (never commit)
├── .gitignore               # Secured environment/system files
├── requirements.txt
├── amd-hackathon-*.json     # Firebase service account (never commit)
├── test_fireworks.py        # Cloud connection diagnostic script
├── list_models.py           # Fireworks API model discovery script
├── src/
│   ├── config.py            # Global timeouts, models, thresholds
│   ├── fireworks_client.py  # Retry-wrapped Fireworks API calls
│   ├── schemas.py           # Expected JSON shapes for both agents
│   ├── pipeline.py          # Orchestrates routing, cache, and Firebase telemetry
│   ├── chat_worker.py       # Daemon linking Firebase RTDB to the LLM pipeline
│   ├── cache/
│   │   ├── firestore_client.py  # Singleton Firebase init
│   │   ├── semantic_cache.py    # FAISS Embedding + cosine similarity lookup
│   └── agents/
│       ├── feature_extractor.py   # Analyzes prompt syntax/domain
│       ├── routing_engine.py      # Evaluates complexity and assigns tier
│       ├── goal_understanding.py  # Goal Understanding Agent
│       └── task_planning.py       # Task Planning Agent
└── logs/
    └── run_logs.jsonl       # Local structured telemetry fallback
Chat Worker Integration (Frontend-Backend Bridge)
To connect the frontend chat app to the backend AI pipeline, we utilize a chat worker daemon. This worker listens to Firebase Realtime Database for new messages and responds autonomously.
Bash
# To start the chat worker daemon (Initializes FAISS and Firebase)
python src/chat_worker.py
Leave this running in a terminal. When a user requests a task via the UI, the worker triggers the pipeline, handles the cache/routing logic, and replies with the generated JSON plan.
Known Limitations
Cloud Timeouts: For highly complex prompts (e.g., full REST API generation), DeepSeek-V4-Pro requires up to 90 seconds. Do not decrease REQUEST_TIMEOUT_CLOUD in config.py.
First-Run Latency: The very first prompt triggering the cloud tier may experience slight initialization latency before returning the response. Subsequent identical prompts resolve in ~0.01s via FAISS.
Embedding cost: Every cache miss triggers feature extraction and inference. Token metrics track cloud execution costs natively.
