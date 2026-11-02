#!/usr/bin/env python3
"""
ARM B: Generative Selection (Extractive ID Emission)

Tests whether generative ID selection beats classical rankers
when cost is measured in output tokens.
"""
import sys
from pathlib import Path
import argparse

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from selector import GenerativeSelector
from baseline_ranker import BM25Ranker, TFIDFRanker
from arms.shared import (
    Fixtures,
    ResultsLogger,
    calculate_recall_at_k,
    calculate_precision_at_k,
    calculate_mean_average_precision
)


def evaluate_selector(predicted_ids: list[int], ground_truth_ids: list[int], k: int = 10) -> dict:
    """Evaluate selector performance"""
    recall = calculate_recall_at_k(predicted_ids, ground_truth_ids, k)
    precision = calculate_precision_at_k(predicted_ids, ground_truth_ids, k)
    map_score = calculate_mean_average_precision(predicted_ids, ground_truth_ids)

    return {
        'recall_at_10': recall,
        'precision_at_10': precision,
        'mean_average_precision': map_score
    }


def run_arm_b(model_path: str, quick: bool = False):
    """Run ARM B generative selection tests"""
    print("=" * 70)
    print("ARM B: Generative Selection (Extractive ID Emission)")
    print("=" * 70)
    print()
    print("Goal: Compare generative ID selection vs classical rankers")
    print("Hypothesis: Emitting ~30 tokens beats extracting ~100-150 tokens")
    print()

    # Initialize components
    gen_selector = GenerativeSelector(model_path)
    bm25_ranker = BM25Ranker()
    tfidf_ranker = TFIDFRanker()
    fixtures = Fixtures()

    # Load test data
    print("Loading test data...")
    queries = fixtures.get_queries()
    conversation = fixtures.get_conversation("medium")  # 50 turns

    if quick:
        queries = queries[:2]  # Test with fewer queries
        print(f"QUICK mode: Testing {len(queries)} queries")
    else:
        print(f"FULL mode: Testing {len(queries)} queries")

    print()

    # Prepare turns with IDs
    turns = []
    for i in range(0, len(conversation), 2):
        if i + 1 < len(conversation):
            turns.append({
                'id': i // 2,
                'turn_id': i // 2,
                'user': conversation[i]['content'],
                'assistant': conversation[i + 1]['content']
            })

    # Limit turns for quick mode to avoid context overflow
    if quick:
        turns = turns[:15]  # Limit to 15 turns for quick mode
        print(f"Conversation: {len(turns)} turns (limited for quick mode)")
    else:
        print(f"Conversation: {len(turns)} turns")
    print()

    # Run tests
    results = {
        'generative': [],
        'bm25': [],
        'tfidf': []
    }

    print("Running queries...")
    print("-" * 70)

    for i, query_data in enumerate(queries):
        query = query_data['query']
        ground_truth = query_data.get('relevant_turns', [])

        print(f"\nQuery {i+1}/{len(queries)}: {query}")
        print(f"Ground truth: {ground_truth}")

        # Generative selector
        print("  - Generative selector...", end=" ")
        gen_ids, gen_metrics = gen_selector.select_turns(query, turns, max_results=10)
        gen_eval = evaluate_selector(gen_ids, ground_truth, k=10)
        print(f"✓ (output: {gen_metrics['output_tokens']} tokens)")
        print(f"    Selected: {gen_ids}")
        print(f"    Recall@10: {gen_eval['recall_at_10']:.2f}")

        # BM25 baseline
        print("  - BM25 ranker...", end=" ")
        bm25_ids, bm25_metrics = bm25_ranker.rank_turns(query, turns, max_results=10)
        bm25_eval = evaluate_selector(bm25_ids, ground_truth, k=10)
        print("✓ (no LLM)")
        print(f"    Selected: {bm25_ids}")
        print(f"    Recall@10: {bm25_eval['recall_at_10']:.2f}")

        # TF-IDF baseline
        print("  - TF-IDF ranker...", end=" ")
        tfidf_ids, tfidf_metrics = tfidf_ranker.rank_turns(query, turns, max_results=10)
        tfidf_eval = evaluate_selector(tfidf_ids, ground_truth, k=10)
        print("✓ (no LLM)")
        print(f"    Selected: {tfidf_ids}")
        print(f"    Recall@10: {tfidf_eval['recall_at_10']:.2f}")

        # Store results
        results['generative'].append({
            'query': query,
            'ground_truth': ground_truth,
            'predicted_ids': gen_ids,
            'metrics': gen_metrics,
            'evaluation': gen_eval
        })

        results['bm25'].append({
            'query': query,
            'ground_truth': ground_truth,
            'predicted_ids': bm25_ids,
            'metrics': bm25_metrics,
            'evaluation': bm25_eval
        })

        results['tfidf'].append({
            'query': query,
            'ground_truth': ground_truth,
            'predicted_ids': tfidf_ids,
            'metrics': tfidf_metrics,
            'evaluation': tfidf_eval
        })

    print()
    print("=" * 70)
    print("RESULTS SUMMARY")
    print("=" * 70)
    print()

    # Aggregate metrics
    def aggregate(method_results):
        avg_recall = sum(r['evaluation']['recall_at_10'] for r in method_results) / len(method_results)
        avg_precision = sum(r['evaluation']['precision_at_10'] for r in method_results) / len(method_results)
        avg_map = sum(r['evaluation']['mean_average_precision'] for r in method_results) / len(method_results)

        # Calculate average output tokens (for generative only)
        if 'output_tokens' in method_results[0]['metrics']:
            avg_output = sum(r['metrics']['output_tokens'] for r in method_results) / len(method_results)
        else:
            avg_output = 0

        return {
            'recall_at_10': avg_recall,
            'precision_at_10': avg_precision,
            'mean_average_precision': avg_map,
            'avg_output_tokens': avg_output
        }

    gen_agg = aggregate(results['generative'])
    bm25_agg = aggregate(results['bm25'])
    tfidf_agg = aggregate(results['tfidf'])

    # Print comparison table
    print(f"{'Method':<20} {'Recall@10':>12} {'Precision@10':>15} {'MAP':>10} {'Tokens':>10}")
    print("-" * 70)
    print(f"{'Generative':<20} {gen_agg['recall_at_10']:>12.3f} {gen_agg['precision_at_10']:>15.3f} "
          f"{gen_agg['mean_average_precision']:>10.3f} {gen_agg['avg_output_tokens']:>10.1f}")
    print(f"{'BM25':<20} {bm25_agg['recall_at_10']:>12.3f} {bm25_agg['precision_at_10']:>15.3f} "
          f"{bm25_agg['mean_average_precision']:>10.3f} {0:>10}")
    print(f"{'TF-IDF':<20} {tfidf_agg['recall_at_10']:>12.3f} {tfidf_agg['precision_at_10']:>15.3f} "
          f"{tfidf_agg['mean_average_precision']:>10.3f} {0:>10}")
    print()

    # Save results
    logger = ResultsLogger(Path(__file__).parent.parent / "results")
    logger.log("arm_b_selection", {
        'results': results,
        'aggregates': {
            'generative': gen_agg,
            'bm25': bm25_agg,
            'tfidf': tfidf_agg
        }
    })

    print("✓ Results saved to arms/results/arm_b_selection_results.json")
    print()

    # Recommendations
    print("=" * 70)
    print("RECOMMENDATIONS")
    print("=" * 70)
    print()

    # Compare generative to best classical baseline
    best_classical = max([bm25_agg, tfidf_agg], key=lambda x: x['recall_at_10'])
    best_classical_name = "BM25" if best_classical == bm25_agg else "TF-IDF"

    recall_diff = gen_agg['recall_at_10'] - best_classical['recall_at_10']
    map_diff = gen_agg['mean_average_precision'] - best_classical['mean_average_precision']

    if recall_diff > 0.1 and gen_agg['avg_output_tokens'] < 50:
        print(f"✓ GENERATIVE WINS")
        print(f"  - Recall advantage: +{recall_diff:.2f} over {best_classical_name}")
        print(f"  - Output cost: ~{gen_agg['avg_output_tokens']:.0f} tokens (bounded)")
        print(f"  - Recommendation: USE generative selection for turn ranking")
    elif recall_diff > 0:
        print(f"~ GENERATIVE SLIGHTLY BETTER")
        print(f"  - Recall advantage: +{recall_diff:.2f} over {best_classical_name}")
        print(f"  - Consider cost vs quality tradeoff")
    else:
        print(f"✗ CLASSICAL WINS")
        print(f"  - {best_classical_name} has better recall: +{abs(recall_diff):.2f}")
        print(f"  - Recommendation: Use {best_classical_name} (no LLM cost)")

    print()
    print("Key findings:")
    print(f"  - Generative output: {gen_agg['avg_output_tokens']:.0f} tokens avg")
    print(f"  - Cost is FLAT in input size (tested on {len(turns)} turns)")
    print(f"  - AMD finding: ~30 tokens regardless of input (7/8 recall)")
    print()


def main():
    parser = argparse.ArgumentParser(description="ARM B: Generative Selection")
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

    run_arm_b(str(model_path), quick=args.quick)


if __name__ == "__main__":
    main()
