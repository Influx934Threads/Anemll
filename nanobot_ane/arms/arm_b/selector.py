"""Generative ID selector for turn and fact ranking"""
import sys
from pathlib import Path
import json
import re
import asyncio

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from ane_inference import ANEInference
from arms.shared import TokenCounter, PromptTemplates


class GenerativeSelector:
    """
    Generative ID selection for retrieval

    Instead of embedding-based similarity search, use LLM to
    directly emit IDs of relevant items.

    Key advantage (from AMD findings):
    - Output is bounded (~30 tokens regardless of input size)
    - Cost is flat in input size (unlike multi-pass abstraction)
    """

    def __init__(self, model_path: str):
        self.inference = ANEInference(model_path)
        self.token_counter = TokenCounter()

    def select_turns(
        self,
        query: str,
        turns: list[dict],
        max_results: int = 10
    ) -> tuple[list[int], dict]:
        """
        Select relevant turn IDs for a query

        Args:
            query: User query
            turns: List of turn dicts with 'id', 'user', 'assistant' keys
            max_results: Maximum number of IDs to return

        Returns:
            (selected_ids, metrics)
        """
        # Format turns with IDs
        turns_text = self._format_turns_with_ids(turns)

        # Build prompt
        prompt = PromptTemplates.TURN_ID_SELECTOR.format(
            query=query,
            turns_with_ids=turns_text
        )

        # Count input tokens
        input_tokens = self.token_counter.count(prompt)

        # Generate (async)
        output = asyncio.run(self.inference.generate(
            prompt=prompt,
            max_tokens=100,  # Should only need ~30 for IDs
            temperature=0.0
        ))

        # Count output tokens
        output_tokens = self.token_counter.count(output)

        # Parse IDs from output
        selected_ids = self._parse_ids(output, max_results)

        metrics = {
            'input_tokens': input_tokens,
            'output_tokens': output_tokens,
            'num_turns': len(turns),
            'num_selected': len(selected_ids)
        }

        return selected_ids, metrics

    def select_facts(
        self,
        query: str,
        facts: list[dict],
        max_results: int = 10
    ) -> tuple[list[int], dict]:
        """
        Select relevant fact IDs for a query

        Args:
            query: User query
            facts: List of fact dicts with 'id', 'type', 'content' keys
            max_results: Maximum number of IDs to return

        Returns:
            (selected_ids, metrics)
        """
        # Format facts with IDs
        facts_text = self._format_facts_with_ids(facts)

        # Build prompt
        prompt = PromptTemplates.FACT_ID_SELECTOR.format(
            query=query,
            facts_with_ids=facts_text
        )

        # Count input tokens
        input_tokens = self.token_counter.count(prompt)

        # Generate (async)
        output = asyncio.run(self.inference.generate(
            prompt=prompt,
            max_tokens=100,
            temperature=0.0
        ))

        # Count output tokens
        output_tokens = self.token_counter.count(output)

        # Parse IDs
        selected_ids = self._parse_ids(output, max_results)

        metrics = {
            'input_tokens': input_tokens,
            'output_tokens': output_tokens,
            'num_facts': len(facts),
            'num_selected': len(selected_ids)
        }

        return selected_ids, metrics

    def _format_turns_with_ids(self, turns: list[dict]) -> str:
        """Format turns with IDs for prompt"""
        lines = []
        for turn in turns:
            turn_id = turn.get('id', turn.get('turn_id', 0))
            user_msg = turn.get('user', turn.get('content', ''))
            asst_msg = turn.get('assistant', '')

            lines.append(f"[{turn_id}] User: {user_msg}")
            if asst_msg:
                lines.append(f"    Assistant: {asst_msg}")

        return '\n'.join(lines)

    def _format_facts_with_ids(self, facts: list[dict]) -> str:
        """Format facts with IDs for prompt"""
        lines = []
        for fact in facts:
            fact_id = fact.get('id', 0)
            fact_type = fact.get('type', 'unknown')
            content = fact.get('content', '')

            lines.append(f"[{fact_id}] ({fact_type}) {content}")

        return '\n'.join(lines)

    def _parse_ids(self, output: str, max_results: int) -> list[int]:
        """
        Parse ID list from model output

        Handles various formats:
        - JSON array: [1, 5, 12]
        - Comma-separated: 1, 5, 12
        - Newline-separated: 1\n5\n12
        """
        ids = []

        # Try JSON first
        try:
            # Extract JSON array from output
            json_match = re.search(r'\[[\d,\s]+\]', output)
            if json_match:
                ids = json.loads(json_match.group())
                return ids[:max_results]
        except (json.JSONDecodeError, AttributeError):
            pass

        # Try comma/space separated numbers
        numbers = re.findall(r'\d+', output)
        ids = [int(n) for n in numbers]

        return ids[:max_results]
