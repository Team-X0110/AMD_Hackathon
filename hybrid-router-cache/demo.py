"""
demo.py — Checkpoint 5 demo sequence.

Runs four prompts that prove the cache layer works end-to-end:
  1. Fresh unique prompt   → cache_hit: none,              tokens > 0
  2. Same prompt again     → cache_hit: exact (both),      tokens = 0
  3. Reworded version      → cache_hit: semantic (goal),   tokens = 0
  4. Unrelated prompt      → cache_hit: none,              tokens > 0

This four-run sequence is the clearest possible proof of token savings.
Screenshot or record it for your demo slide.

Usage:
    cd hybrid-router-cache
    python demo.py
"""
import json
from src.pipeline import run_pipeline

SEPARATOR = "─" * 72

PROMPTS = [
    # Run 1 — cold start
    "Build a REST API for a todo app with user authentication and JWT tokens",

    # Run 2 — exact same string → exact cache hit
    "Build a REST API for a todo app with user authentication and JWT tokens",

    # Run 3 — paraphrase → semantic cache hit (same meaning, different words)
    "Create a RESTful backend service for task management with login and JWT-based auth",

    # Run 4 — completely different → another cold start
    "Design a real-time chat application with WebSocket support and message persistence",
]

LABELS = [
    "Run 1 — Fresh unique prompt   (expect: cache_hit = none, tokens > 0)",
    "Run 2 — Same prompt again     (expect: cache_hit = exact, tokens = 0)",
    "Run 3 — Paraphrased prompt    (expect: cache_hit = semantic, tokens = 0)",
    "Run 4 — Unrelated prompt      (expect: cache_hit = none, tokens > 0)",
]


def print_result(label: str, prompt: str, result: dict) -> None:
    print(f"\n{SEPARATOR}")
    print(f"  {label}")
    print(f"  Prompt: {prompt[:70]}...")
    print(SEPARATOR)
    print(f"  Goal cache hit : {result['cache_hits']['goal']}")
    print(f"  Plan cache hit : {result['cache_hits']['plan']}")
    print(f"  Tokens used    : {result['tokens_used']}")
    print(f"  Latency        : {result['latency_sec']:.3f}s")
    print()


def main():
    print("\n" + "=" * 72)
    print("  HYBRID ROUTER CACHE — Demo (Checkpoint 5)")
    print("=" * 72)

    total_tokens_with_cache = 0
    total_tokens_without_cache = 0

    for label, prompt in zip(LABELS, PROMPTS):
        result = run_pipeline(prompt)
        print_result(label, prompt, result)
        total_tokens_with_cache += result["tokens_used"]

    # Rough estimate: without cache every run would cost ~1200 tokens (400 goal + 800 plan)
    total_tokens_without_cache = 1200 * len(PROMPTS)
    tokens_saved = total_tokens_without_cache - total_tokens_with_cache
    savings_pct = 100 * tokens_saved / total_tokens_without_cache

    print("=" * 72)
    print(f"  SUMMARY")
    print(f"  Tokens used (with cache)    : {total_tokens_with_cache}")
    print(f"  Tokens would cost (no cache): ~{total_tokens_without_cache}")
    print(f"  Tokens saved                : ~{tokens_saved} (~{savings_pct:.0f}%)")
    print("=" * 72)


if __name__ == "__main__":
    main()
