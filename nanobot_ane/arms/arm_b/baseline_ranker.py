"""Classical ranking baselines for comparison"""
from collections import Counter
import math
import re
from typing import List, Dict, Any


class BM25Ranker:
    """
    BM25 ranking algorithm

    Classical information retrieval baseline.
    No LLM, no embeddings - just term frequency statistics.
    """

    def __init__(self, k1: float = 1.5, b: float = 0.75):
        """
        Args:
            k1: Term frequency saturation parameter (default 1.5)
            b: Length normalization parameter (default 0.75)
        """
        self.k1 = k1
        self.b = b
        self.idf_cache = {}
        self.avg_doc_len = 0

    def rank_turns(
        self,
        query: str,
        turns: List[Dict[str, Any]],
        max_results: int = 10
    ) -> tuple[List[int], dict]:
        """
        Rank turns using BM25

        Args:
            query: User query
            turns: List of turn dicts
            max_results: Maximum results to return

        Returns:
            (ranked_turn_ids, metrics)
        """
        # Build documents (concatenate user + assistant for each turn)
        documents = []
        for turn in turns:
            user_msg = turn.get('user', turn.get('content', ''))
            asst_msg = turn.get('assistant', '')
            doc = f"{user_msg} {asst_msg}"
            documents.append(doc)

        # Compute BM25 scores
        scores = self._compute_bm25(query, documents)

        # Sort by score (descending)
        scored_turns = [(turn.get('id', turn.get('turn_id', i)), score)
                        for i, (turn, score) in enumerate(zip(turns, scores))]
        scored_turns.sort(key=lambda x: x[1], reverse=True)

        # Extract top IDs
        ranked_ids = [turn_id for turn_id, score in scored_turns[:max_results]]

        metrics = {
            'num_turns': len(turns),
            'num_selected': len(ranked_ids),
            'top_score': scored_turns[0][1] if scored_turns else 0,
            'method': 'bm25'
        }

        return ranked_ids, metrics

    def rank_facts(
        self,
        query: str,
        facts: List[Dict[str, Any]],
        max_results: int = 10
    ) -> tuple[List[int], dict]:
        """
        Rank facts using BM25

        Args:
            query: User query
            facts: List of fact dicts
            max_results: Maximum results to return

        Returns:
            (ranked_fact_ids, metrics)
        """
        # Extract fact content as documents
        documents = [fact.get('content', '') for fact in facts]

        # Compute BM25 scores
        scores = self._compute_bm25(query, documents)

        # Sort by score
        scored_facts = [(fact.get('id', i), score)
                        for i, (fact, score) in enumerate(zip(facts, scores))]
        scored_facts.sort(key=lambda x: x[1], reverse=True)

        # Extract top IDs
        ranked_ids = [fact_id for fact_id, score in scored_facts[:max_results]]

        metrics = {
            'num_facts': len(facts),
            'num_selected': len(ranked_ids),
            'top_score': scored_facts[0][1] if scored_facts else 0,
            'method': 'bm25'
        }

        return ranked_ids, metrics

    def _compute_bm25(self, query: str, documents: List[str]) -> List[float]:
        """
        Compute BM25 scores for query against documents

        Returns:
            List of scores (one per document)
        """
        # Tokenize
        query_terms = self._tokenize(query)
        doc_terms = [self._tokenize(doc) for doc in documents]

        # Compute average document length
        self.avg_doc_len = sum(len(terms) for terms in doc_terms) / len(doc_terms) if doc_terms else 0

        # Compute IDF for query terms
        num_docs = len(documents)
        for term in query_terms:
            if term not in self.idf_cache:
                # Count documents containing term
                df = sum(1 for terms in doc_terms if term in terms)
                # IDF formula: log((N - df + 0.5) / (df + 0.5) + 1)
                idf = math.log((num_docs - df + 0.5) / (df + 0.5) + 1)
                self.idf_cache[term] = idf

        # Compute BM25 score for each document
        scores = []
        for terms in doc_terms:
            score = 0
            term_freq = Counter(terms)
            doc_len = len(terms)

            for query_term in query_terms:
                if query_term in term_freq:
                    tf = term_freq[query_term]
                    idf = self.idf_cache.get(query_term, 0)

                    # BM25 formula
                    numerator = tf * (self.k1 + 1)
                    denominator = tf + self.k1 * (1 - self.b + self.b * doc_len / self.avg_doc_len)
                    score += idf * (numerator / denominator)

            scores.append(score)

        return scores

    def _tokenize(self, text: str) -> List[str]:
        """Simple tokenization (lowercased words)"""
        # Remove punctuation and lowercase
        text = re.sub(r'[^\w\s]', ' ', text.lower())
        # Split on whitespace
        tokens = text.split()
        return tokens


class TFIDFRanker:
    """
    TF-IDF ranking baseline

    Simpler than BM25, useful for comparison.
    """

    def __init__(self):
        self.idf_cache = {}

    def rank_turns(
        self,
        query: str,
        turns: List[Dict[str, Any]],
        max_results: int = 10
    ) -> tuple[List[int], dict]:
        """Rank turns using TF-IDF"""
        # Build documents
        documents = []
        for turn in turns:
            user_msg = turn.get('user', turn.get('content', ''))
            asst_msg = turn.get('assistant', '')
            doc = f"{user_msg} {asst_msg}"
            documents.append(doc)

        # Compute TF-IDF scores
        scores = self._compute_tfidf(query, documents)

        # Sort and return top IDs
        scored_turns = [(turn.get('id', turn.get('turn_id', i)), score)
                        for i, (turn, score) in enumerate(zip(turns, scores))]
        scored_turns.sort(key=lambda x: x[1], reverse=True)

        ranked_ids = [turn_id for turn_id, score in scored_turns[:max_results]]

        return ranked_ids, {'method': 'tfidf'}

    def rank_facts(
        self,
        query: str,
        facts: List[Dict[str, Any]],
        max_results: int = 10
    ) -> tuple[List[int], dict]:
        """Rank facts using TF-IDF"""
        documents = [fact.get('content', '') for fact in facts]

        scores = self._compute_tfidf(query, documents)

        scored_facts = [(fact.get('id', i), score)
                        for i, (fact, score) in enumerate(zip(facts, scores))]
        scored_facts.sort(key=lambda x: x[1], reverse=True)

        ranked_ids = [fact_id for fact_id, score in scored_facts[:max_results]]

        return ranked_ids, {'method': 'tfidf'}

    def _compute_tfidf(self, query: str, documents: List[str]) -> List[float]:
        """Compute TF-IDF scores"""
        query_terms = self._tokenize(query)
        doc_terms = [self._tokenize(doc) for doc in documents]

        # Compute IDF
        num_docs = len(documents)
        for term in set(sum(doc_terms, [])):  # All unique terms
            df = sum(1 for terms in doc_terms if term in terms)
            self.idf_cache[term] = math.log(num_docs / (df + 1))

        # Compute TF-IDF
        scores = []
        for terms in doc_terms:
            score = 0
            term_freq = Counter(terms)
            max_tf = max(term_freq.values()) if term_freq else 1

            for query_term in query_terms:
                if query_term in term_freq:
                    tf = term_freq[query_term] / max_tf  # Normalized TF
                    idf = self.idf_cache.get(query_term, 0)
                    score += tf * idf

            scores.append(score)

        return scores

    def _tokenize(self, text: str) -> List[str]:
        """Simple tokenization"""
        text = re.sub(r'[^\w\s]', ' ', text.lower())
        return text.split()
