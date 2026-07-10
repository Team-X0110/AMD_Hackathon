"""
agents/routing_engine.py — Evaluates complexity, risk, and decides the model tier.
"""

class RoutingEngine:
    def __init__(self):
        pass

    def evaluate(self, features: dict) -> dict:
        """
        Calculates Complexity (Task 3.3) and determines Model Tier (Task 3.4).
        """
        complexity = 1
        risk = "low"
        
        # Length Penalties (Relaxed)
        if features['word_count'] > 200:
            complexity += 3
        elif features['word_count'] > 100:
            complexity += 1

        # Domain & Structural Penalties (Tuned for Cost Efficiency)
        if features['domain'] == 'code_creation':
            complexity += 2  # Reduced penalty so simple code routes locally
            risk = "medium"
        elif features['domain'] == 'mathematics':
            complexity += 3
            risk = "high" 

        if features['has_code_block']:
            complexity += 2
            
        if features['requires_json']:
            complexity += 1

        # Cap the score at a maximum of 10
        complexity = min(complexity, 10)

        # -----------------------------------------
        # Confidence Engine: Aggressively favor LOCAL
        # -----------------------------------------
        selected_tier = "local" # Default to 0 tokens
        
        if complexity >= 8:
            selected_tier = "large"
        elif complexity >= 6:
            selected_tier = "medium"
        elif complexity >= 4:
            selected_tier = "small"

        return {
            "complexity_score": complexity,
            "risk_level": risk,
            "routed_tier": selected_tier
        }