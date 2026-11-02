"""Generative retrieval as primary retrieval mechanism"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from arms.arm_b.selector import GenerativeSelector


class GenerativeRetriever:
    """
    Use generative selection as the PRIMARY retrieval mechanism

    AMD Finding: "Generative selection as this box's general retrieval
    primitive — possibly the most consequential item here."

    Argument:
    - Embedding retrieval failed (paraphrase queries at chance)
    - Generative selection succeeded (7/8 for ~27 tokens)
    - Under 39x cost ratio, flat-cost generative beats continuous embedding

    This class wraps GenerativeSelector to provide retrieval interface.
    """

    def __init__(self, model_path: str):
        self.selector = GenerativeSelector(model_path)

    def search_turns(
        self,
        query: str,
        conversation_history: list[dict],
        k: int = 10
    ) -> tuple[list[dict], dict]:
        """
        Search conversation history using generative selection

        Args:
            query: User search query
            conversation_history: List of turns
            k: Number of results to return

        Returns:
            (relevant_turns, metrics)
        """
        # Prepare turns with IDs
        turns = []
        for i, turn in enumerate(conversation_history):
            turns.append({
                'id': i,
                'turn_id': i,
                'user': turn.get('user', turn.get('content', '')),
                'assistant': turn.get('assistant', '')
            })

        # Use generative selector
        selected_ids, metrics = self.selector.select_turns(query, turns, max_results=k)

        # Retrieve full turns
        relevant_turns = [turns[tid] for tid in selected_ids if tid < len(turns)]

        return relevant_turns, metrics

    def search_facts(
        self,
        query: str,
        fact_database: list[dict],
        k: int = 10
    ) -> tuple[list[dict], dict]:
        """
        Search fact database using generative selection

        Args:
            query: User search query
            fact_database: List of facts
            k: Number of results to return

        Returns:
            (relevant_facts, metrics)
        """
        # Ensure facts have IDs
        facts = []
        for i, fact in enumerate(fact_database):
            fact_with_id = fact.copy()
            if 'id' not in fact_with_id:
                fact_with_id['id'] = i
            facts.append(fact_with_id)

        # Use generative selector
        selected_ids, metrics = self.selector.select_facts(query, facts, max_results=k)

        # Retrieve full facts
        relevant_facts = [facts[fid] for fid in selected_ids if fid < len(facts)]

        return relevant_facts, metrics


class CostModel:
    """
    Cost modeling for generative vs embedding retrieval

    Determines break-even point: when does generative cost less?
    """

    def __init__(
        self,
        embedding_index_time_ms: float,
        embedding_index_interval_s: float,
        generative_query_time_ms: float,
        embedding_query_time_ms: float
    ):
        """
        Args:
            embedding_index_time_ms: Time to build embedding index
            embedding_index_interval_s: How often index is rebuilt (e.g., 2700s = 45min)
            generative_query_time_ms: Time per generative query
            embedding_query_time_ms: Time per embedding query
        """
        self.embedding_index_time_ms = embedding_index_time_ms
        self.embedding_index_interval_s = embedding_index_interval_s
        self.generative_query_time_ms = generative_query_time_ms
        self.embedding_query_time_ms = embedding_query_time_ms

    def cost_over_time(self, time_period_s: float, queries_per_period: int) -> dict:
        """
        Calculate total cost over a time period

        Returns:
            {
                'embedding_total_ms': total time for embedding path,
                'generative_total_ms': total time for generative path,
                'winner': 'embedding' or 'generative'
            }
        """
        # Embedding path cost
        num_index_rebuilds = time_period_s / self.embedding_index_interval_s
        embedding_index_cost = num_index_rebuilds * self.embedding_index_time_ms
        embedding_query_cost = queries_per_period * self.embedding_query_time_ms
        embedding_total = embedding_index_cost + embedding_query_cost

        # Generative path cost (no indexing, just query time)
        generative_total = queries_per_period * self.generative_query_time_ms

        winner = 'generative' if generative_total < embedding_total else 'embedding'

        return {
            'embedding_total_ms': embedding_total,
            'embedding_index_cost_ms': embedding_index_cost,
            'embedding_query_cost_ms': embedding_query_cost,
            'generative_total_ms': generative_total,
            'winner': winner,
            'savings_ms': embedding_total - generative_total if winner == 'generative' else generative_total - embedding_total,
            'savings_pct': abs(embedding_total - generative_total) / max(embedding_total, generative_total) * 100
        }

    def break_even_queries(self, time_period_s: float) -> int:
        """
        Calculate break-even point: how many queries before generative wins?

        Returns:
            Number of queries where costs are equal
        """
        num_index_rebuilds = time_period_s / self.embedding_index_interval_s
        embedding_index_cost = num_index_rebuilds * self.embedding_index_time_ms

        # Solve: embedding_index_cost + Q * embedding_query_time = Q * generative_query_time
        # Q * (generative_query_time - embedding_query_time) = embedding_index_cost
        # Q = embedding_index_cost / (generative_query_time - embedding_query_time)

        denominator = self.generative_query_time_ms - self.embedding_query_time_ms

        if denominator <= 0:
            # Generative is always slower per query
            return float('inf')

        break_even = embedding_index_cost / denominator

        return int(break_even)
