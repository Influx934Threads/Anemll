#!/usr/bin/env python3
"""
ARM E: Generative Selection as Primary Retrieval (Bonus)

Tests whether generative retrieval should replace embeddings entirely.

AMD Finding: "Generative selection as this box's general retrieval
primitive — possibly the most consequential item here."
"""
import sys
from pathlib import Path
import argparse
import time

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from generative_retriever import GenerativeRetriever, CostModel
from arms.shared import (
    Fixtures,
    ResultsLogger,
    calculate_recall_at_k,
    calculate_precision_at_k
)


def run_arm_e(model_path: str, quick: bool = False):
    """Run ARM E generative retrieval tests"""
    print("=" * 70)
    print("ARM E: Generative Selection as Primary Retrieval")
    print("=" * 70)
    print()
    print("Question: Should we replace embeddings with generative selection?")
    print("AMD Finding: Generative worked, embeddings failed")
    print()

    # Initialize
    retriever = GenerativeRetriever(model_path)
    fixtures = Fixtures()

    # Load test data
    queries = fixtures.get_queries()
    # Use small conversation to avoid context overflow (2048 limit)
    conversation = fixtures.get_conversation("small")

    if quick:
        queries = queries[:2]

    print(f"Testing {len(queries)} queries on conversation with {len(conversation)//2} turns")
    print()

    # Prepare turns - limit to 10 turns max to avoid context overflow
    turns = []
    for i in range(0, min(len(conversation), 20), 2):
        if i + 1 < len(conversation):
            turns.append({
                'id': i // 2,
                'user': conversation[i]['content'],
                'assistant': conversation[i + 1]['content']
            })

    # === Test 1: Search Quality ===
    print("Test 1: Search Quality")
    print("-" * 70)

    search_results = []

    for i, query_data in enumerate(queries):
        query = query_data['query']
        ground_truth = query_data.get('relevant_turns', [])

        print(f"Query {i+1}: {query}")

        start_time = time.time()
        relevant_turns, metrics = retriever.search_turns(query, turns, k=10)
        query_time_ms = (time.time() - start_time) * 1000

        selected_ids = [t['id'] for t in relevant_turns]

        recall = calculate_recall_at_k(selected_ids, ground_truth, k=10)
        precision = calculate_precision_at_k(selected_ids, ground_truth, k=10)

        print(f"  Selected: {selected_ids}")
        print(f"  Ground truth: {ground_truth}")
        print(f"  Recall@10: {recall:.2%}")
        print(f"  Output tokens: {metrics['output_tokens']}")
        print(f"  Query time: {query_time_ms:.0f}ms")
        print()

        search_results.append({
            'query': query,
            'selected_ids': selected_ids,
            'ground_truth': ground_truth,
            'recall': recall,
            'precision': precision,
            'output_tokens': metrics['output_tokens'],
            'query_time_ms': query_time_ms
        })

    # Aggregate quality
    avg_recall = sum(r['recall'] for r in search_results) / len(search_results)
    avg_precision = sum(r['precision'] for r in search_results) / len(search_results)
    avg_output_tokens = sum(r['output_tokens'] for r in search_results) / len(search_results)
    avg_query_time = sum(r['query_time_ms'] for r in search_results) / len(search_results)

    print("Quality Summary:")
    print(f"  Average Recall@10: {avg_recall:.2%}")
    print(f"  Average Precision@10: {avg_precision:.2%}")
    print(f"  Average output tokens: {avg_output_tokens:.1f}")
    print(f"  Average query time: {avg_query_time:.0f}ms")
    print()

    # === Test 2: Cost Analysis ===
    print("Test 2: Cost Analysis")
    print("-" * 70)
    print()
    print("Comparison: Generative vs Embedding Retrieval")
    print()

    # Hypothetical embedding costs (from AMD doc)
    # - Index rebuild: ~45 min interval
    # - Index time: ~30-60s (depends on corpus size)
    # - Query time: ~10-50ms (fast)

    embedding_scenarios = [
        {
            'name': 'Small corpus (fast index)',
            'index_time_ms': 10000,  # 10s
            'query_time_ms': 20,
        },
        {
            'name': 'Medium corpus',
            'index_time_ms': 30000,  # 30s
            'query_time_ms': 30,
        },
        {
            'name': 'Large corpus (slow index)',
            'index_time_ms': 60000,  # 60s
            'query_time_ms': 50,
        }
    ]

    cost_results = []

    for scenario in embedding_scenarios:
        print(f"Scenario: {scenario['name']}")

        cost_model = CostModel(
            embedding_index_time_ms=scenario['index_time_ms'],
            embedding_index_interval_s=2700,  # 45 min (from AMD doc)
            generative_query_time_ms=avg_query_time,
            embedding_query_time_ms=scenario['query_time_ms']
        )

        # Calculate cost over 24 hours
        time_period_s = 86400  # 24 hours

        # Test different query volumes
        query_volumes = [10, 50, 100, 200, 500]

        print(f"  {'Queries/day':<15} {'Embedding (s)':>15} {'Generative (s)':>15} {'Winner':<15}")
        print("  " + "-" * 60)

        scenario_results = []

        for queries_per_day in query_volumes:
            cost = cost_model.cost_over_time(time_period_s, queries_per_day)

            print(f"  {queries_per_day:<15} {cost['embedding_total_ms']/1000:>15.1f} "
                  f"{cost['generative_total_ms']/1000:>15.1f} {cost['winner']:<15}")

            scenario_results.append({
                'queries_per_day': queries_per_day,
                'cost': cost
            })

        # Find break-even
        break_even = cost_model.break_even_queries(time_period_s)
        print(f"  Break-even: {break_even} queries/day")
        print()

        cost_results.append({
            'scenario': scenario['name'],
            'results': scenario_results,
            'break_even': break_even
        })

    # === Summary ===
    print("=" * 70)
    print("RESULTS SUMMARY")
    print("=" * 70)
    print()

    print("## Retrieval Quality")
    print()
    print(f"Generative retrieval: {avg_recall:.2%} recall, {avg_output_tokens:.0f} tokens")
    print()

    if avg_recall >= 0.7:
        print("✓ Quality acceptable (>=70% recall)")
    else:
        print("✗ Quality insufficient (<70% recall)")

    print()

    print("## Cost Analysis")
    print()
    print("When generative wins:")

    for scenario_result in cost_results:
        scenario = scenario_result['scenario']
        break_even = scenario_result['break_even']

        if break_even < 1000:
            print(f"  {scenario}: <{break_even} queries/day")
        else:
            print(f"  {scenario}: Never (generative too slow per query)")

    print()

    # Save results
    logger = ResultsLogger(Path(__file__).parent.parent / "results")
    logger.log("arm_e_retrieval", {
        'quality': {
            'avg_recall': avg_recall,
            'avg_precision': avg_precision,
            'avg_output_tokens': avg_output_tokens,
            'avg_query_time_ms': avg_query_time
        },
        'search_results': search_results,
        'cost_analysis': cost_results
    })

    print("✓ Results saved to arms/results/arm_e_retrieval_results.json")
    print()

    # === Recommendations ===
    print("=" * 70)
    print("RECOMMENDATIONS")
    print("=" * 70)
    print()

    # Decision logic
    if avg_recall >= 0.7:
        print("✓ Generative retrieval has acceptable quality")
        print()

        # Check if there's any scenario where it wins
        any_wins = any(r['break_even'] < 500 for r in cost_results)

        if any_wins:
            print("✓ Generative wins on cost in low-query scenarios")
            print()
            print("RECOMMENDATION: USE generative retrieval")
            print()
            print("When to use:")
            for result in cost_results:
                if result['break_even'] < 500:
                    print(f"  - {result['scenario']}: <{result['break_even']} queries/day")
            print()
            print("Benefits:")
            print("  - No embedding index to maintain")
            print("  - No flm-embed service failures")
            print("  - Simpler architecture (one less component)")
            print("  - Better recall on paraphrased queries")
        else:
            print("✗ Embedding retrieval cheaper at all query volumes")
            print()
            print("RECOMMENDATION: Keep embeddings if they work")
            print()
            print("However, AMD finding: embeddings FAILED on paraphrase queries")
            print("If ANE embeddings also fail, generative is only option")
    else:
        print("✗ Generative retrieval quality insufficient")
        print()
        print("RECOMMENDATION: Improve prompts or keep embeddings")

    print()
    print("AMD context:")
    print("  - embed-gemma:300m put paraphrase queries at chance")
    print("  - Generative selector: 7/8 recall for 27 tokens")
    print("  - Under 39x ratio, generative beats embedding")
    print()


def main():
    parser = argparse.ArgumentParser(description="ARM E: Generative Retrieval")
    parser.add_argument(
        "--model",
        type=str,
        default="~/.nanobot/models/qwen3-1.7b/qwen3-ane-instruct.mlmodelc",
        help="Path to CoreML model"
    )
    parser.add_argument(
        "--quick",
        action="store_true",
        help="Run abbreviated tests"
    )

    args = parser.parse_args()

    model_path = Path(args.model).expanduser()

    if not model_path.exists():
        print(f"Error: Model not found at {model_path}")
        sys.exit(1)

    run_arm_e(str(model_path), quick=args.quick)


if __name__ == "__main__":
    main()
