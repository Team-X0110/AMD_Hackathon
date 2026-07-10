# AMD Hackathon — AI Chat Pipeline

A full-stack real-time chat application powered by an AI planning pipeline. Users send messages through a React chat UI; a Python backend worker picks up each message, runs it through a two-agent LLM pipeline (Goal Understanding → Task Planning), and replies as **AMD Bot** — all in real-time via Firebase.

---

## Architecture Overview

```
┌─────────────────────────────┐        Firebase Realtime DB        ┌──────────────────────────────────┐
│   Frontend (Vite + React)   │  ──── messages/{chatId} ────►      │  Backend Worker (Python)         │
│                             │                                     │                                  │
│  • AMDChat UI               │  ◄─── bot reply ─────────────────  │  • Listens for new messages      │
│  • Firebase Auth            │                                     │  • Runs run_pipeline(prompt)     │
│  • Real-time message sync   │                                     │  • Exact + Semantic Cache        │
└─────────────────────────────┘                                     │  • Writes bot reply to RTDB      │
                                                                    └──────────────────────────────────┘
```

### AI Pipeline (inside the backend worker)

```
User Message
     │
     ▼
[Exact Cache]  ──── hit ────► return cached result  (0 tokens)
     │ miss
     ▼
[Semantic Cache (cosine ≥ 0.92)] ── hit ──► return closest match (0 tokens)
     │ miss
     ▼
[LLM Call — Ollama local or Fireworks cloud]
     │
     ▼
Agent 1: Goal Understanding  →  structured goal JSON
     │
     ▼
Agent 2: Task Planning  →  dependency graph + effort estimates
     │
     ▼
AMD Bot replies in chat with the plan + cache metrics
```

---

## Repository Structure

```
amd_hacathon/
├── frontend/                        # Vite + React chat app
│   ├── src/
│   │   ├── App.tsx                  # Root component + provider stack
│   │   ├── firebase.ts              # Firebase SDK init
│   │   ├── components/
│   │   │   ├── ChatWindow.tsx       # Message UI (send, edit, delete, search)
│   │   │   ├── Sidebar.tsx          # Conversation list + user profile
│   │   │   ├── AuthScreen.tsx       # Sign in / sign up / anonymous login
│   │   │   └── FirebaseSetup.tsx    # First-run Firebase config UI
│   │   └── context/
│   │       ├── AuthContext.tsx      # Auth state, auto anonymous sign-in
│   │       ├── FirebaseConfigContext.tsx  # Config: env → localStorage → UI
│   │       └── ThemeContext.tsx     # Light / dark mode
│   ├── .env.example                 # Template for Firebase env vars
│   └── package.json
│
└── hybrid-router-cache/             # Python AI pipeline + chat worker
    ├── src/
    │   ├── pipeline.py              # Main entry: run_pipeline(prompt) → {goal, tasks, cache_hits}
    │   ├── chat_worker.py           # Daemon: listens to RTDB, calls pipeline, replies as AMD Bot
    │   ├── config.py                # All settings (models, thresholds, collection names)
    │   ├── fireworks_client.py      # Unified LLM client (Ollama local / Fireworks cloud)
    │   ├── validators.py            # Schema + DAG cycle detection (Kahn's algorithm)
    │   ├── agents/
    │   │   ├── goal_understanding.py
    │   │   └── task_planning.py
    │   └── cache/
    │       ├── exact_cache.py       # SHA-256 hash cache via Firebase RTDB
    │       ├── semantic_cache.py    # Cosine similarity cache via embeddings
    │       └── firestore_client.py  # Firebase RTDB init (singleton)
    ├── tests/
    ├── logs/
    ├── requirements.txt
    └── .env
```

---

## Prerequisites

- Python 3.11+
- Node.js 18+ and npm
- [Ollama](https://ollama.ai) running locally **or** a Fireworks AI API key
- A Firebase project with Realtime Database enabled
- Firebase service account JSON (for the Python backend)

---

## Setup

### 1. Backend (Python)

```bash
cd hybrid-router-cache

# Install dependencies
pip install -r requirements.txt

# Configure environment
# Edit .env with your values:
#   LLM_BACKEND=local            (or "fireworks")
#   FIREBASE_KEY_PATH=<path-to-your-service-account.json>
#   FIREWORKS_API_KEY=<key>      (only if LLM_BACKEND=fireworks)

# If using Ollama (local), pull the model first:
ollama pull llama3.1:8b
```

**`.env` reference:**

```dotenv
LLM_BACKEND=local                          # "local" (Ollama) or "fireworks"
OLLAMA_URL=http://localhost:11434/api/chat
LOCAL_MODEL=llama3.1:8b
FIREWORKS_API_KEY=your_key_here            # only needed for LLM_BACKEND=fireworks
FIREBASE_KEY_PATH=amd-hackathon-c23d8-firebase-adminsdk-fbsvc-7f33dd39d1.json
FIREBASE_PROJECT_ID=amd-hackathon-c23d8
```

### 2. Frontend (React)

```bash
cd frontend

# Install dependencies
npm install

# Configure Firebase
cp .env.example .env
# Fill in your Firebase project values in .env
```

**`frontend/.env` reference:**

```dotenv
VITE_FIREBASE_API_KEY=<your-api-key>
VITE_FIREBASE_AUTH_DOMAIN=<project-id>.firebaseapp.com
VITE_FIREBASE_DATABASE_URL=https://<project-id>-default-rtdb.<region>.firebasedatabase.app
VITE_FIREBASE_PROJECT_ID=<project-id>
VITE_FIREBASE_STORAGE_BUCKET=<project-id>.firebasestorage.app
VITE_FIREBASE_MESSAGING_SENDER_ID=<sender-id>
VITE_FIREBASE_APP_ID=<app-id>
```

Find these values in [Firebase Console](https://console.firebase.google.com) → Project Settings → Your apps → Web app config.

---

## Running the Application

You need **three** terminals:

**Terminal 1 — Ollama (if using local backend):**
```bash
ollama serve
```

**Terminal 2 — Python chat worker:**
```bash
cd hybrid-router-cache
python src/chat_worker.py
```

**Terminal 3 — Frontend dev server:**
```bash
cd frontend
npm run dev
```

Then open `http://localhost:5173`, create a chat room, and send a message. AMD Bot will reply with a structured task plan within seconds.

---

## How the Bot Responds

When you send a message, AMD Bot replies with a formatted plan like:

```
🤖 AMD Bot  |  ⚡ none  |  🎯 none  |  🪙 523 tokens  |  ⏱ 4.21s

🎯 Goal
Intent: Build a REST API for a todo app
Domain: software engineering
Complexity: medium

📋 Task Plan

  t1 [S] Design API schema
       └─ deps: none

  t2 [M] Implement authentication endpoints
       └─ deps: t1

  t3 [M] Implement todo CRUD endpoints
       └─ deps: t1

  t4 [S] Write API tests
       └─ deps: t2, t3

⚡ Parallel groups: [t2, t3] → [t4]
```

Cache hit labels:
- `exact` — identical prompt seen before, 0 tokens used
- `semantic(0.94)` — paraphrase matched, 0 tokens used
- `none` — fresh LLM call, tokens consumed

---

## Running Tests

```bash
cd hybrid-router-cache
python -m pytest tests/ -v
```

## Demo (Cache Behavior)

```bash
cd hybrid-router-cache
python demo.py
```

Runs 4 prompts in sequence to demonstrate the full cache chain:
1. Fresh prompt → `cache_hit: none`, tokens > 0
2. Same prompt again → `cache_hit: exact`, tokens = 0
3. Reworded version → `cache_hit: semantic(0.9x)`, tokens = 0
4. Unrelated prompt → `cache_hit: none`, tokens > 0

---

## Configuration Reference

| Variable | Location | Description |
|---|---|---|
| `LLM_BACKEND` | `hybrid-router-cache/.env` | `local` (Ollama) or `fireworks` |
| `LOCAL_MODEL` | `hybrid-router-cache/.env` | Ollama model name (default: `llama3.1:8b`) |
| `FIREWORKS_API_KEY` | `hybrid-router-cache/.env` | Fireworks AI key (cloud mode only) |
| `FIREBASE_KEY_PATH` | `hybrid-router-cache/.env` | Path to Firebase service account JSON |
| `SEMANTIC_THRESHOLD` | `src/config.py` | Cosine similarity cutoff (default: `0.92`) |
| `CACHE_LOOKBACK_LIMIT` | `src/config.py` | Max entries scanned for semantic match (default: `100`) |
| `VITE_FIREBASE_*` | `frontend/.env` | Firebase config for the React frontend |

---

## Known Limitations

- **Semantic search is O(N)** — scans up to `CACHE_LOOKBACK_LIMIT` entries in-memory. Fine for hackathon scale; use a vector DB for production.
- **No message backlog processing** — the chat worker only responds to messages that arrive after it starts.
- **Single worker process** — concurrent chats are handled sequentially. For production, use a task queue (Celery, Cloud Tasks).
