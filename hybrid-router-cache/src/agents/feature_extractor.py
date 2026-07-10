"""
agents/feature_extractor.py — Extracts structural and linguistic signals from prompts.
"""
import re

class FeatureExtractor:
    def __init__(self):
        # Keyword sets for fast intent categorization
        self.creation_verbs = {"write", "build", "generate", "create", "develop", "implement", "code"}
        self.analysis_verbs = {"explain", "summarize", "debug", "analyze", "format", "fix", "review"}
        self.math_keywords = {"calculate", "equation", "formula", "derive", "compute", "math"}

    def extract(self, prompt: str) -> dict:
        """
        Parses the prompt and returns a dictionary of routing signals.
        Zero LLM calls, pure Python execution.
        """
        prompt_lower = prompt.lower()
        # Extract alphanumeric words
        words = set(re.findall(r'\b\w+\b', prompt_lower))

        # 1. Textual Metrics
        char_length = len(prompt)
        word_count = len(words)
        
        # 2. Structural Heuristics
        # Triple backticks strongly indicate a code generation or debugging task
        has_code_block = bool(re.search(r'```', prompt))
        requires_json = "json" in words
        requires_jwt = "jwt" in words
        
        # 3. Intent Classification
        domain = "general"
        if words.intersection(self.creation_verbs) or has_code_block:
            domain = "code_creation"
        elif words.intersection(self.analysis_verbs):
            domain = "code_analysis"
        elif words.intersection(self.math_keywords):
            domain = "mathematics"

        # 4. Rough Complexity Signal (Can be tuned later)
        # Longer prompts with specific formatting constraints are usually more complex
        complexity_flags = sum([has_code_block, requires_json, requires_jwt])
        is_complex = (word_count > 100) or (complexity_flags >= 2)

        return {
            "char_length": char_length,
            "word_count": word_count,
            "has_code_block": has_code_block,
            "requires_json": requires_json,
            "domain": domain,
            "is_complex": is_complex
        }