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
