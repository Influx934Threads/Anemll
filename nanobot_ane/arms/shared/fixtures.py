"""Test data fixtures for NPU investigation"""
from pathlib import Path
import json
from typing import List, Dict, Any


class Fixtures:
    """Shared test data for all arms"""

    def __init__(self, fixtures_dir: Path = None):
        if fixtures_dir is None:
            fixtures_dir = Path(__file__).parent / "fixtures"
        self.fixtures_dir = Path(fixtures_dir)
        self.fixtures_dir.mkdir(parents=True, exist_ok=True)

    def get_conversation(self, size: str = "medium") -> List[Dict[str, Any]]:
        """
        Get test conversation

        Args:
            size: "small" (10 turns, ~2K tokens)
                  "medium" (50 turns, ~8K tokens)
                  "large" (100 turns, ~16K tokens)

        Returns:
            List of message dicts with 'role' and 'content'
        """
        path = self.fixtures_dir / f"conversation_{size}.json"

        if not path.exists():
            # Generate synthetic conversation if not exists
            return self._generate_conversation(size)

        with open(path, 'r') as f:
            return json.load(f)

    def get_facts(self, count: int = 50) -> List[Dict[str, Any]]:
        """
        Get test facts with ground truth labels

        Returns:
            List of fact dicts with 'type', 'content', 'entities', 'turn_id'
        """
        path = self.fixtures_dir / "facts_labeled.json"

        if not path.exists():
            return self._generate_facts(count)

        with open(path, 'r') as f:
            facts = json.load(f)
            return facts[:count]

    def get_queries(self) -> List[Dict[str, Any]]:
        """
        Get test queries with ground truth relevant turn IDs

        Returns:
            List of dicts: {"query": "...", "relevant_turns": [1, 5, 12], ...}
        """
        path = self.fixtures_dir / "queries_labeled.json"

        if not path.exists():
            return self._generate_queries()

        with open(path, 'r') as f:
            return json.load(f)

    def save_conversation(self, messages: List[Dict[str, Any]], size: str):
        """Save conversation to fixtures"""
        path = self.fixtures_dir / f"conversation_{size}.json"
        with open(path, 'w') as f:
            json.dump(messages, f, indent=2)

    def save_facts(self, facts: List[Dict[str, Any]]):
        """Save facts to fixtures"""
        path = self.fixtures_dir / "facts_labeled.json"
        with open(path, 'w') as f:
            json.dump(facts, f, indent=2)

    def save_queries(self, queries: List[Dict[str, Any]]):
        """Save queries to fixtures"""
        path = self.fixtures_dir / "queries_labeled.json"
        with open(path, 'w') as f:
            json.dump(queries, f, indent=2)

    def _generate_conversation(self, size: str) -> List[Dict[str, Any]]:
        """Generate synthetic conversation for testing"""
        size_map = {
            "small": 10,
            "medium": 50,
            "large": 100
        }
        num_turns = size_map.get(size, 50)

        messages = []
        topics = [
            ("timeout configuration", "30 seconds"),
            ("log level", "debug mode"),
            ("database connection", "PostgreSQL on port 5432"),
            ("cache size", "1024 MB"),
            ("API rate limit", "100 requests per minute"),
            ("retry policy", "3 attempts with exponential backoff"),
            ("authentication method", "OAuth 2.0"),
            ("session timeout", "15 minutes of inactivity"),
            ("maximum file size", "50 MB"),
            ("backup schedule", "daily at 2 AM UTC")
        ]

        for i in range(num_turns):
            topic, detail = topics[i % len(topics)]

            # User message
            messages.append({
                "role": "user",
                "content": f"Can you set the {topic} to {detail}?"
            })

            # Assistant message
            messages.append({
                "role": "assistant",
                "content": f"I've configured the {topic} to {detail}. The change has been applied and will take effect immediately."
            })

        self.save_conversation(messages, size)
        return messages

    def _generate_facts(self, count: int) -> List[Dict[str, Any]]:
        """Generate synthetic facts for testing"""
        fact_templates = [
            {"type": "configuration", "content": "timeout set to {value}", "entities": ["timeout"]},
            {"type": "preference", "content": "user prefers {value}", "entities": ["preference"]},
            {"type": "threshold", "content": "maximum {resource} is {value}", "entities": ["threshold"]},
            {"type": "requirement", "content": "system must support {feature}", "entities": ["requirement"]},
            {"type": "decision", "content": "chose {option} over {alternative}", "entities": ["decision"]},
        ]

        values = ["30 seconds", "debug mode", "100 MB", "PostgreSQL", "OAuth 2.0"]
        resources = ["memory", "connections", "file size", "requests"]
        features = ["TLS 1.3", "HTTP/2", "gRPC", "GraphQL"]

        facts = []
        for i in range(count):
            template = fact_templates[i % len(fact_templates)]
            fact = template.copy()

            # Fill in template values based on content
            content = fact["content"]

            if "{resource}" in content and "{value}" in content:
                fact["content"] = content.format(
                    resource=resources[i % len(resources)],
                    value=values[i % len(values)]
                )
            elif "{option}" in content and "{alternative}" in content:
                fact["content"] = content.format(
                    option=features[i % len(features)],
                    alternative=features[(i + 1) % len(features)]
                )
            elif "{feature}" in content:
                fact["content"] = content.format(feature=features[i % len(features)])
            elif "{value}" in content:
                fact["content"] = content.format(value=values[i % len(values)])

            fact["turn_id"] = i // 2  # Two facts per turn
            facts.append(fact)

        self.save_facts(facts)
        return facts

    def _generate_queries(self) -> List[Dict[str, Any]]:
        """Generate synthetic queries with ground truth"""
        queries = [
            {
                "query": "What is the timeout configuration?",
                "relevant_turns": [0, 1, 2],
                "relevant_facts": [0, 1, 2]
            },
            {
                "query": "Which authentication method are we using?",
                "relevant_turns": [6, 7],
                "relevant_facts": [12, 13]
            },
            {
                "query": "What are the database settings?",
                "relevant_turns": [2, 3],
                "relevant_facts": [4, 5, 6]
            },
            {
                "query": "Tell me about rate limiting",
                "relevant_turns": [4, 5],
                "relevant_facts": [8, 9]
            },
            {
                "query": "What retry policy is configured?",
                "relevant_turns": [5, 6],
                "relevant_facts": [10, 11]
            }
        ]

        self.save_queries(queries)
        return queries


class PromptTemplates:
    """Prompt templates for different compression strategies"""

    # ARM D: Token budgeting prompts
    BASELINE_FACT_EXTRACTION = """Extract facts from this conversation turn. Be concise and specific.

Turn:
{turn_text}

Facts:"""

    D1_STRICT_BUDGET = """Extract facts from this conversation turn. Respond with ≤50 tokens.
Use extreme concision. Omit articles, use abbreviations where clear.

Turn:
{turn_text}

Facts (≤50 tokens):"""

    D2_JSON_STRUCTURED = """Extract facts as JSON array. Each fact: {{"t": "type", "c": "content"}}.
Types: req (requirement), cfg (configuration), thresh (threshold), pref (preference), dec (decision).

Turn:
{turn_text}

JSON:"""

    D3_ENTITY_IDS = """Extract entities and assign short IDs. Respond with ID mappings only.
Use format: ID: entity=value

Turn:
{turn_text}

Entities:"""

    D4_TAGGED_FACTS = """Extract facts with type tags. Format: [TYPE] content
Types: REQ, CFG, THRESH, PREF, DEC

Turn:
{turn_text}

Facts:"""

    # ARM B: Generative selection prompts
    TURN_ID_SELECTOR = """Given this conversation history with turn IDs, emit ONLY the IDs of turns
relevant to the query. Respond with a JSON array of integers, nothing else.

Query: {query}

Turns:
{turns_with_ids}

Relevant turn IDs (JSON array):"""

    FACT_ID_SELECTOR = """Given these facts with IDs, emit ONLY the IDs of facts relevant to the query.
Respond with a JSON array of integers, nothing else.

Query: {query}

Facts:
{facts_with_ids}

Relevant fact IDs (JSON array):"""

    # ARM C: Map-mechanical-merge prompts
    STRUCTURED_FACT_EXTRACTION = """Extract facts from this conversation turn as structured JSON.

Each fact must have:
- type: one of [requirement, configuration, threshold, preference, decision, context, task, result]
- content: the actual fact (be specific, include numbers/names)
- entities: list of key entities mentioned (e.g., ["timeout", "database"])

Turn:
{turn_text}

JSON (array of facts):"""

    CONSOLIDATION_BASELINE = """Merge these facts into a coherent summary. Be extremely concise.
Aggressively remove duplicates. Preserve specific numbers and names.
Keep summary under 75 words.

Facts:
{facts_text}

Summary:"""
