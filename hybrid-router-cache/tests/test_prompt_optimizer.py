from src.prompt_optimizer import PromptOptimizer, estimate_tokens, optimize_prompt_pair


def test_estimate_tokens_is_positive_for_simple_text():
    assert estimate_tokens("hello world") >= 2


def test_optimize_prompt_pair_removes_redundancy_and_trims():
    system_prompt = "You are an agent. You are an agent. Return JSON only."
    user_prompt = "Build a todo API. Build a todo API. Build a todo API. Add auth."

    optimized_system, optimized_user = optimize_prompt_pair(
        system_prompt,
        user_prompt,
        max_system_tokens=12,
        max_user_tokens=12,
    )

    assert len(optimized_system.split()) <= len(system_prompt.split())
    assert len(optimized_user.split()) <= len(user_prompt.split())
    assert "json" in optimized_system.lower()
    assert "todo api" in optimized_user.lower()
    assert "auth" in optimized_user.lower()


def test_dynamic_prompt_generation_keeps_core_intent():
    optimizer = PromptOptimizer()
    compact_prompt = optimizer.build_dynamic_prompt(
        "You are a helpful assistant. Return JSON only.",
        "Please build a todo API. Please build a todo API.",
    )

    assert "json" in compact_prompt.lower()
    assert "todo api" in compact_prompt.lower()
    assert len(compact_prompt.split()) < 20
