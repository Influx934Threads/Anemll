"""Structured fact extraction for map-mechanical-merge"""
import sys
from pathlib import Path
import json
import re
import asyncio

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from ane_inference import ANEInference
from arms.shared import TokenCounter, PromptTemplates


class StructuredFactExtractor:
    """
    Extract facts as structured JSON for mechanical merging

    Instead of free-form prose, emit structured data:
    {
        "type": "configuration",
        "content": "timeout set to 30 seconds",
        "entities": ["timeout", "30 seconds"]
    }

    This enables CPU-side merging without needing a second LLM pass.
    """

    def __init__(self, model_path: str):
        self.inference = ANEInference(model_path)
        self.token_counter = TokenCounter()

    def extract_facts(self, turn_text: str, max_tokens: int = 200) -> tuple[list[dict], dict]:
        """
        Extract structured facts from a turn

        Args:
            turn_text: Conversation turn (user + assistant)
            max_tokens: Maximum output tokens

        Returns:
            (facts_list, metrics)
        """
        # Build prompt
        prompt = PromptTemplates.STRUCTURED_FACT_EXTRACTION.format(
            turn_text=turn_text
        )

        # Count input tokens
        input_tokens = self.token_counter.count(prompt)

        # Generate (async)
        output = asyncio.run(self.inference.generate(
            prompt=prompt,
            max_tokens=max_tokens,
            temperature=0.0
        ))

        # Count output tokens
        output_tokens = self.token_counter.count(output)

        # Parse JSON output
        facts = self._parse_facts(output)

        metrics = {
            'input_tokens': input_tokens,
            'output_tokens': output_tokens,
            'num_facts_extracted': len(facts)
        }

        return facts, metrics

    def _parse_facts(self, output: str) -> list[dict]:
        """
        Parse structured facts from JSON output

        Handles various formats and recovers from malformed JSON
        """
        facts = []

        # Try parsing as JSON array
        try:
            # Extract JSON array from output (may have extra text)
            json_match = re.search(r'\[.*\]', output, re.DOTALL)
            if json_match:
                facts = json.loads(json_match.group())
                return facts
        except json.JSONDecodeError:
            pass

        # Try parsing as multiple JSON objects (one per line)
        try:
            for line in output.split('\n'):
                line = line.strip()
                if line.startswith('{') and line.endswith('}'):
                    fact = json.loads(line)
                    facts.append(fact)
        except json.JSONDecodeError:
            pass

        # Fallback: parse as free-form text and structure it
        if not facts:
            facts = self._parse_freeform(output)

        return facts

    def _parse_freeform(self, output: str) -> list[dict]:
        """
        Fallback parser for free-form output

        Attempts to structure unstructured fact text
        """
        facts = []

        # Split by lines and treat each non-empty line as a fact
        for line in output.split('\n'):
            line = line.strip()

            # Skip empty lines and markdown headers
            if not line or line.startswith('#'):
                continue

            # Remove bullet points
            line = re.sub(r'^[-*•]\s*', '', line)

            # Infer type from keywords
            fact_type = self._infer_type(line)

            # Extract entities (simple heuristic)
            entities = self._extract_entities(line)

            facts.append({
                'type': fact_type,
                'content': line,
                'entities': entities
            })

        return facts

    def _infer_type(self, text: str) -> str:
        """Infer fact type from content"""
        text_lower = text.lower()

        if any(word in text_lower for word in ['require', 'must', 'should', 'need']):
            return 'requirement'
        elif any(word in text_lower for word in ['configure', 'set', 'config', 'enable', 'disable']):
            return 'configuration'
        elif any(word in text_lower for word in ['maximum', 'minimum', 'limit', 'threshold']):
            return 'threshold'
        elif any(word in text_lower for word in ['prefer', 'like', 'want']):
            return 'preference'
        elif any(word in text_lower for word in ['decide', 'chose', 'selected']):
            return 'decision'
        elif any(word in text_lower for word in ['task', 'todo', 'action']):
            return 'task'
        elif any(word in text_lower for word in ['result', 'output', 'completed']):
            return 'result'
        else:
            return 'context'

    def _extract_entities(self, text: str) -> list[str]:
        """Extract key entities from text (simple heuristic)"""
        entities = []

        # Extract numbers with units
        numbers = re.findall(r'\d+(?:\.\d+)?\s*(?:ms|sec|seconds|MB|KB|GB|min|minutes|hours)', text)
        entities.extend(numbers)

        # Extract capitalized words (potential proper nouns)
        capitalized = re.findall(r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b', text)
        entities.extend(capitalized)

        # Extract quoted strings
        quoted = re.findall(r'"([^"]+)"', text)
        entities.extend(quoted)

        return entities[:5]  # Limit to 5 entities
