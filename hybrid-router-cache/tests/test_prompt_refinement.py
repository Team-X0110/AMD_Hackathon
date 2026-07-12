import pytest
from unittest.mock import patch, MagicMock
from src.agents.prompt_refinement import refine_prompt
from pydantic import ValidationError

@patch("src.agents.prompt_refinement.get_routing_engine")
def test_refine_prompt_success(mock_get_engine):
    mock_engine = MagicMock()
    mock_get_engine.return_value = mock_engine

    class MockTokenUsage:
        total_tokens = 50
        fireworks_tokens = 0

    class MockOutcome:
        def model_dump(self):
            return {"tier": "local", "status": "success"}

    mock_engine.execute_with_escalation.return_value = (
        {
            "refined_prompt": "Build a React app",
            "ambiguity_resolved": True,
            "changes_made": ["Fixed typos", "Resolved ambiguity"]
        },
        MockTokenUsage(),
        [MockOutcome()]
    )

    result = refine_prompt("buid reat ap")
    
    assert "refinement" in result
    assert result["refinement"]["refined_prompt"] == "Build a React app"
    assert result["tokens_used"] == 50
    assert result["fireworks_tokens"] == 0
    assert len(result["routing"]) == 1
    
    mock_engine.execute_with_escalation.assert_called_once()
    kwargs = mock_engine.execute_with_escalation.call_args.kwargs
    assert kwargs["agent"] == "refinement"
    assert kwargs["text"] == "buid reat ap"
