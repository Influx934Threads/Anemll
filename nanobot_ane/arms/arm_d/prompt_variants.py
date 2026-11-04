"""Prompt variants for token budget optimization"""
import sys
import asyncio
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from ane_inference import ANEInference
from arms.shared import TokenCounter


class PromptVariant:
    """Base class for prompt variants"""

    def __init__(self, model_path: str):
        self.inference = ANEInference(model_path)
        self.token_counter = TokenCounter()
        self.name = "base"
        self.description = "Base prompt variant"

    def extract_facts(self, turn_text: str, max_tokens: int = 200) -> tuple[str, dict]:
        """
        Extract facts using this prompt variant

        Returns:
            (output_text, metrics)
        """
        raise NotImplementedError

    def _measure(self, prompt: str, max_tokens: int) -> tuple[str, dict]:
        """Helper to measure inference"""
        input_tokens = self.token_counter.count(prompt)

        output = asyncio.run(self.inference.generate(
            prompt=prompt,
            max_tokens=max_tokens,
            temperature=0.0
        ))

        output_tokens = self.token_counter.count(output)

        metrics = {
            'variant': self.name,
            'input_tokens': input_tokens,
            'output_tokens': output_tokens,
            'max_tokens_allowed': max_tokens
        }

        return output, metrics


class BaselineVariant(PromptVariant):
    """Baseline: Current prompt (no explicit budget)"""

    def __init__(self, model_path: str):
        super().__init__(model_path)
        self.name = "baseline"
        self.description = "Current prompts (no explicit token budget)"

    def extract_facts(self, turn_text: str, max_tokens: int = 200) -> tuple[str, dict]:
        prompt = f"""Extract facts from this conversation turn. Be concise and specific.

Turn:
{turn_text}

Facts:"""

        return self._measure(prompt, max_tokens)


class D1StrictBudget(PromptVariant):
    """D1: Hard token budget constraint"""

    def __init__(self, model_path: str):
        super().__init__(model_path)
        self.name = "d1_strict"
        self.description = "Hard budget: ≤50 tokens, extreme concision"

    def extract_facts(self, turn_text: str, max_tokens: int = 50) -> tuple[str, dict]:
        prompt = f"""Extract facts from this conversation turn. Respond with ≤50 tokens.
Use extreme concision. Omit articles, use abbreviations where clear.

Turn:
{turn_text}

Facts (≤50 tokens):"""

        return self._measure(prompt, max_tokens)


class D2JSONStructured(PromptVariant):
    """D2: JSON structured output (implicit compression)"""

    def __init__(self, model_path: str):
        super().__init__(model_path)
        self.name = "d2_json"
        self.description = "JSON structure: implicit compression via format"

    def extract_facts(self, turn_text: str, max_tokens: int = 100) -> tuple[str, dict]:
        prompt = f"""Extract facts as JSON array. Each fact: {{"t": "type", "c": "content"}}.
Types: req (requirement), cfg (configuration), thresh (threshold), pref (preference), dec (decision).
Be concise.

Turn:
{turn_text}

JSON:"""

        return self._measure(prompt, max_tokens)


class D3EntityIDs(PromptVariant):
    """D3: Entity ID mapping (maximum compression)"""

    def __init__(self, model_path: str):
        super().__init__(model_path)
        self.name = "d3_ids"
        self.description = "Entity IDs: maximum compression via ID assignment"

    def extract_facts(self, turn_text: str, max_tokens: int = 60) -> tuple[str, dict]:
        prompt = f"""Extract entities and assign short IDs. Respond with ID mappings only.
Use format: ID: entity=value

Turn:
{turn_text}

Entities:"""

        return self._measure(prompt, max_tokens)


class D4TaggedFacts(PromptVariant):
    """D4: Tagged facts with type prefixes"""

    def __init__(self, model_path: str):
        super().__init__(model_path)
        self.name = "d4_tagged"
        self.description = "Tagged facts: [TYPE] content format"

    def extract_facts(self, turn_text: str, max_tokens: int = 100) -> tuple[str, dict]:
        prompt = f"""Extract facts with type tags. Format: [TYPE] content
Types: REQ, CFG, THRESH, PREF, DEC

Turn:
{turn_text}

Facts:"""

        return self._measure(prompt, max_tokens)


class D5BulletPoints(PromptVariant):
    """D5: Ultra-concise bullet points"""

    def __init__(self, model_path: str):
        super().__init__(model_path)
        self.name = "d5_bullets"
        self.description = "Ultra-concise bullets: shortest possible format"

    def extract_facts(self, turn_text: str, max_tokens: int = 70) -> tuple[str, dict]:
        prompt = f"""Extract key facts as ultra-concise bullet points. Maximum brevity.
Omit unnecessary words. Keep only essential info.

Turn:
{turn_text}

•"""

        return self._measure(prompt, max_tokens)


def get_all_variants(model_path: str) -> list[PromptVariant]:
    """Get all prompt variants for testing"""
    return [
        BaselineVariant(model_path),
        D1StrictBudget(model_path),
        D2JSONStructured(model_path),
        D3EntityIDs(model_path),
        D4TaggedFacts(model_path),
        D5BulletPoints(model_path)
    ]
