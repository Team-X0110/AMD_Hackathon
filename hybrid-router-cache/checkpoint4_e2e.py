import json
from src.agents.goal_understanding import understand_goal_with_semantic
from src.agents.task_planning import plan_tasks_with_semantic
from src.cache.firestore_client import get_db

def test_e2e():
    print("Testing Goal Understanding Agent...")
    prompt = "Create a real-time chat application using React, Node.js, and WebSocket. Must use MongoDB."
    
    # 1. Goal Understanding
    print(f"\nUser Prompt: {prompt}")
    goal_res = understand_goal_with_semantic(prompt)
    
    print("\n--- Goal Output ---")
    print(json.dumps(goal_res["goal"], indent=2))
    print(f"Cache Hit: {goal_res['cache_hit']}")
    print(f"Tokens Used: {goal_res['tokens_used']}")
    
    # 2. Task Planning
    print("\nTesting Task Planning Agent (using goal output)...")
    plan_res = plan_tasks_with_semantic(goal_res["goal"])
    
    print("\n--- Plan Output ---")
    print(json.dumps(plan_res["tasks"], indent=2))
    print(f"Cache Hit: {plan_res['cache_hit']}")
    print(f"Tokens Used: {plan_res['tokens_used']}")
    
    print("\nEnd-to-End Test Completed Successfully!")

if __name__ == "__main__":
    test_e2e()
