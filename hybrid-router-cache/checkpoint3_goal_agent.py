"""
checkpoint3_goal_agent.py — Phase 3 / Checkpoint 3

Run 10 diverse prompts through understand_goal_with_semantic in isolation.
Outputs results to console AND appends them to logs/checkpoint3_outputs.jsonl.
Eyeball the outputs for schema consistency before wiring the pipeline.

Usage:
    python checkpoint3_goal_agent.py
"""
import json
from pathlib import Path
from src.agents.goal_understanding import understand_goal_with_semantic

LOG_PATH = Path("logs/checkpoint3_outputs.jsonl")
LOG_PATH.parent.mkdir(exist_ok=True)

PROMPTS = [
    "Build a REST API for a todo app with user authentication",
    "Create a machine learning pipeline to classify customer support tickets",
    "Set up a CI/CD pipeline for a React app deployed to AWS",
    "Design a database schema for an e-commerce platform with inventory tracking",
    "Write a web scraper that extracts product prices and emails daily digests",
    "Migrate a monolithic Python Flask app to microservices",
    "Build a real-time dashboard for monitoring server metrics",
    "Create a CLI tool that converts CSV files to SQLite databases",
    "Implement a recommendation engine for a music streaming app",
    "asdf qwer zxcv",  # garbage input — should produce valid JSON, not crash
]

SEPARATOR = "─" * 68


def main():
    print("\n" + "=" * 68)
    print("  Checkpoint 3 — Goal Understanding Agent (10 prompts)")
    print("=" * 68)

    all_ok = True

    for i, prompt in enumerate(PROMPTS, 1):
        print(f"\n[{i}/10] Prompt: {prompt[:60]}{'...' if len(prompt) > 60 else ''}")
        print(SEPARATOR)
        try:
            result = understand_goal_with_semantic(prompt)
            print(f"  cache_hit    : {result['cache_hit']}")
            print(f"  tokens_used  : {result['tokens_used']}")
            print(f"  complexity   : {result['goal']['complexity_hint']}")
            print(f"  intent       : {result['goal']['intent']}")
            print(f"  entities     : {result['goal']['entities']}")

            # Append to log
            LOG_PATH.open("a").write(
                json.dumps({"prompt": prompt, **result}) + "\n"
            )
        except Exception as e:
            print(f"  ❌ ERROR: {e}")
            all_ok = False

    print("\n" + "=" * 68)
    if all_ok:
        print("  ✅ Checkpoint 3 PASSED — all 10 prompts produced valid goal JSON.")
    else:
        print("  ❌ Checkpoint 3 FAILED — review errors above and tighten the system prompt.")
    print(f"  Outputs saved to: {LOG_PATH}")
    print("=" * 68)


if __name__ == "__main__":
    main()
