# Routing Engine · Local Verifier · Reflection Agent
## Architecture Analysis & Implementation Plan

---

## Current State Analysis

The project currently contains:
```
AMD_Hackathon/
├── .env               # Environment config (Ollama local + Fireworks API key + Firebase)
├── README.md          # Empty placeholder
└── model_data/
    └── models.json    # 8 Fireworks models, full metadata (1884 lines)
```

**Models in models.json** (8 total, 5 providers):

| Model | Tier | Cost $/1M in | Cost $/1M out | Latency | Vision |
|---|---|---|---|---|---|
| `deepseek-v4-flash` | Cheap | $0.14 | $0.28 | Ultra Fast | ✗ |
| `minimax-m3` | Balanced | $0.30 | $1.20 | Fast | ✓ |
| `qwen3p7-plus` | Balanced | $0.40 | $1.60 | Fast | ✓ |
| `kimi-k2p7-code` | Premium | $0.95 | $4.00 | Fast | ✓ |
| `kimi-k2p6` | Premium | $0.95 | $4.00 | Fast | ✓ |
| `glm-5p1` | Premium | $1.40 | $4.40 | Fast | ✓ |
| `glm-5p2` | Premium | $1.40 | $4.40 | Fast | ✓ |
| `deepseek-v4-pro` | Ultra Premium | $1.74 | $3.48 | Medium | ✗ |

Local execution uses **Ollama** (cost = $0, URL: `http://localhost:11434/api/chat`).

---

## Architecture Decision

The project is a **Python-only backend** orchestration framework. No frontend is required. The three modules (3.5, 3.6, 3.7) slot into the existing pipeline after the Confidence Engine.

### Why this directory layout?

```
AMD_Hackathon/
├── .env
├── README.md
├── model_data/
│   └── models.json
│
├── config/                          # All YAML/JSON config — no magic numbers in code
│   ├── routing_config.yaml          # Weight vectors, tier thresholds, escalation policy
│   ├── verifier_config.yaml         # Per-strategy thresholds, min quality bars
│   └── reflection_config.yaml       # Retry limits, backoff, failure category → action map
│
├── core/                            # Shared domain types and interfaces (no dependencies)
│   ├── __init__.py
│   ├── types.py                     # All dataclasses/enums shared across modules
│   └── interfaces.py                # ABC contracts that every module must implement
│
├── routing/                         # Module 3.5
│   ├── __init__.py
│   ├── model_registry.py            # Loads + indexes models.json, zero hardcoding
│   ├── utility_scorer.py            # Computes multi-dimensional utility per candidate
│   ├── escalation_policy.py         # Tier ordering + progressive escalation logic
│   ├── routing_engine.py            # Orchestrates registry → scorer → policy → decision
│   └── routing_telemetry.py         # Structured metrics emission for routing decisions
│
├── verification/                    # Module 3.6
│   ├── __init__.py
│   ├── strategies/
│   │   ├── __init__.py
│   │   ├── base_strategy.py         # Abstract verification strategy
│   │   ├── self_consistency.py      # Multi-sample agreement check
│   │   ├── schema_validator.py      # JSON / Pydantic schema validation
│   │   ├── code_validator.py        # AST syntax check + optional unit test runner
│   │   ├── completeness_checker.py  # Minimum content heuristics
│   │   ├── hallucination_detector.py# Statistical + lexical hallucination signals
│   │   ├── format_validator.py      # Output format / length sanity
│   │   └── citation_validator.py    # Citation presence/plausibility check
│   ├── verifier.py                  # Orchestrates all strategies, returns VerificationResult
│   └── verification_telemetry.py    # Structured diagnostics and metrics
│
├── reflection/                      # Module 3.7
│   ├── __init__.py
│   ├── failure_classifier.py        # Categorises WHY verification failed
│   ├── prompt_improver.py           # Rewrites prompts before retry
│   ├── retry_history.py             # Immutable log of all attempts in a session
│   ├── action_resolver.py           # failure_category → ReflectionAction enum
│   └── reflection_agent.py          # Top-level orchestrator: classify→improve→act
│
├── telemetry/                       # Cross-cutting telemetry store
│   ├── __init__.py
│   ├── execution_record.py          # Full per-request execution record dataclass
│   └── telemetry_store.py           # Append-only JSONL file store (future ML-ready)
│
└── tests/                           # Unit tests for all three modules
    ├── test_routing_engine.py
    ├── test_verifier.py
    └── test_reflection_agent.py
```

**Rationale for every top-level directory:**

- `config/` — separates all thresholds/weights from code; change behaviour without touching Python
- `core/` — shared types first; no circular imports; `interfaces.py` defines contracts so modules can be swapped
- `routing/` — fully isolated; only depends on `core/` and `config/`
- `verification/` — strategy pattern inside `strategies/`; adding a new check = add one file, register in config
- `reflection/` — owns retry logic and prompt engineering; no network calls; depends on `core/` and `routing/`
- `telemetry/` — append-only JSONL makes every execution replayable and ML-trainable later

---

## Implementation Order

I will implement files **one at a time**, stopping after each for your confirmation:

| # | File | Why first |
|---|---|---|
| 1 | `config/routing_config.yaml` | All weights/thresholds in one place; everything else reads from it |
| 2 | `config/verifier_config.yaml` | Strategy enablement and per-strategy thresholds |
| 3 | `config/reflection_config.yaml` | Retry limits and failure-category → action mapping |
| 4 | `core/types.py` | All shared dataclasses/enums; no imports from project |
| 5 | `core/interfaces.py` | ABCs; imports only from `core/types.py` |
| 6 | `telemetry/execution_record.py` | Record shape; used by all three modules |
| 7 | `telemetry/telemetry_store.py` | JSONL writer; depended on by all telemetry emitters |
| 8 | `routing/model_registry.py` | Dynamic loader from `models.json` |
| 9 | `routing/utility_scorer.py` | Multi-dimensional weighted scoring engine |
| 10 | `routing/escalation_policy.py` | Tier ordering and progressive escalation |
| 11 | `routing/routing_telemetry.py` | Routing metrics emitter |
| 12 | `routing/routing_engine.py` | Top-level router: registry + scorer + policy + telemetry |
| 13 | `verification/strategies/base_strategy.py` | Abstract base |
| 14 | `verification/strategies/self_consistency.py` | Multi-sample agreement |
| 15 | `verification/strategies/schema_validator.py` | JSON/Pydantic schema |
| 16 | `verification/strategies/code_validator.py` | AST + unit test runner |
| 17 | `verification/strategies/completeness_checker.py` | Content heuristics |
| 18 | `verification/strategies/hallucination_detector.py` | Hallucination signals |
| 19 | `verification/strategies/format_validator.py` | Format/length sanity |
| 20 | `verification/strategies/citation_validator.py` | Citation check |
| 21 | `verification/verification_telemetry.py` | Verification metrics |
| 22 | `verification/verifier.py` | Main verifier orchestrator |
| 23 | `reflection/failure_classifier.py` | Why did it fail? |
| 24 | `reflection/prompt_improver.py` | Auto prompt rewriting |
| 25 | `reflection/retry_history.py` | Immutable attempt log |
| 26 | `reflection/action_resolver.py` | failure → action mapping |
| 27 | `reflection/reflection_agent.py` | Top-level reflection orchestrator |
| 28 | `tests/test_routing_engine.py` | Routing tests |
| 29 | `tests/test_verifier.py` | Verifier tests |
| 30 | `tests/test_reflection_agent.py` | Reflection tests |

---

## Key Design Decisions

### Routing Engine — Utility Score Formula
```
U(model, task) = Σ wᵢ · fᵢ(model, task)

where:
  f1 = quality_score      (from routing_metadata)
  f2 = domain_match       (agent_recommendations[task_type] / 10)
  f3 = reasoning_score    (if task requires reasoning)
  f4 = coding_score       (if task requires coding)
  f5 = vision_score       (if task has image input)
  f6 = token_efficiency   (favours cheaper models at equal quality)
  f7 = latency_score      (favours faster for real-time)
  f8 = cost_penalty       (inverted: higher cost → lower utility)
  f9 = confidence_match   (|task_confidence - model_confidence_threshold|)
  f10 = history_factor    (from rolling success rate telemetry)
  f11 = local_preference  (large constant bonus for Ollama tier)

All fᵢ normalised [0,1]. Weights wᵢ loaded from routing_config.yaml.
```

### Escalation Tiers (fixed order, never skip unless config says so)
```
Tier 0: Local (Ollama)                   cost = 0
Tier 1: Cheap  (deepseek-v4-flash)       cost = $0.14/$0.28
Tier 2: Balanced (minimax-m3, qwen3p7)   cost = $0.30-0.40
Tier 3: Premium (kimi, glm)              cost = $0.95-1.40
Tier 4: Ultra Premium (deepseek-v4-pro)  cost = $1.74
```

### Verification — Strategy Chain
Each strategy returns `StrategyResult(passed, confidence, reasons)`. The verifier aggregates via weighted voting. Minimum overall confidence threshold is configurable per task domain.

### Reflection — Failure → Action Table
| Failure Category | Primary Action |
|---|---|
| `INSUFFICIENT_REASONING` | Retry same model with chain-of-thought injection |
| `HALLUCINATION` | Retry same model with grounding prompt |
| `FORMATTING` | Retry same model with explicit format template |
| `INCORRECT_SCHEMA` | Retry same model with schema example |
| `MISSING_INFORMATION` | Retry with additional context injected |
| `UNSAFE_OUTPUT` | Abort with explanation |
| `TOOL_FAILURE` | Retry with tool simplification or substitute tool |
| `LOW_CONFIDENCE` | Escalate to next tier |
| `POOR_CODE_QUALITY` | Retry coding-specialized model |
| `EXECUTION_FAILURE` | Escalate after 1 retry |

---

## Open Questions

> [!IMPORTANT]
> **Q1: Do the upstream modules (Feature Extractor, Complexity Estimator, Confidence Engine) already have Python files, or are they also being built from scratch?**
> The `.env` and directory structure suggest the project is very early. If those modules exist elsewhere (e.g., another team member's branch), please share their `RoutingContext` / `ConfidenceResult` dataclass signatures so the interfaces match perfectly.

> [!IMPORTANT]
> **Q2: What Python version and package manager?**
> The `.env` has no Python-related config. I'll assume Python 3.11+ with `pip`. If `poetry` or `conda` is in use, let me know.

> [!IMPORTANT]
> **Q3: Should the Reflection Agent be allowed to call Ollama locally for retry, or only Fireworks?**
> The policy states "Local execution costs ZERO" — I'll assume local retries are always permitted, but confirm.

> [!NOTE]
> **Q4: Self-consistency verification** requires multiple model calls. Should this strategy only activate for high-risk tasks (to avoid token cost), or always?
> I'll default it to "only for high_risk=True tasks" unless told otherwise.

---

## Verification Plan

### Automated
- Unit tests for `RoutingEngine.route()` with mock models
- Unit tests for each `VerificationStrategy` independently
- Unit tests for `ReflectionAgent` retry loop with injected failure states

### Integration
- End-to-end test: feed a sample `RoutingContext` through all three modules
- Telemetry output validates correct JSONL record shape

