#!/usr/bin/env python3
"""
ARM D: Output-Token Budgeting and Optimization

Tests different prompt strategies to minimize output tokens
while maintaining quality.
"""
import sys
from pathlib import Path
import argparse

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from prompt_variants import get_all_variants
from validator import OutputValidator, FactCoverageChecker
from arms.shared import Fixtures, ResultsLogger


def run_arm_d(model_path: str, quick: bool = False):
    """Run ARM D token budgeting tests"""
    print("=" * 70)
    print("ARM D: Output-Token Budgeting and Optimization")
    print("=" * 70)
    print()
    print("Goal: Minimize output tokens while maintaining quality")
    print("Hypothesis: Explicit budgets reduce cost without hurting recall")
    print()

    # Initialize
    variants = get_all_variants(model_path)
    validator = OutputValidator()
    coverage_checker = FactCoverageChecker()
    fixtures = Fixtures()

    # Load test data
    conversation = fixtures.get_conversation("small" if quick else "medium")

    # Prepare turns
    turns = []
    for i in range(0, len(conversation), 2):
        if i + 1 < len(conversation):
            turn_text = f"User: {conversation[i]['content']}\nAssistant: {conversation[i+1]['content']}"
            turns.append(turn_text)

    if quick:
        turns = turns[:5]

    print(f"Testing {len(variants)} prompt variants on {len(turns)} turns")
    print()

    # Run tests for each variant
    results = {}

    for variant in variants:
        print(f"Testing variant: {variant.name}")
        print(f"  {variant.description}")
        print("-" * 70)

        variant_results = {
            'name': variant.name,
            'description': variant.description,
            'outputs': [],
            'metrics': [],
            'validations': []
        }

        for i, turn in enumerate(turns):
            print(f"  Turn {i+1}/{len(turns)}...", end=" ")

            # Extract facts
            output, metrics = variant.extract_facts(turn)

            # Validate
            validation = validator.validate(output, turn)
            coverage = coverage_checker.check_coverage(output, turn)

            print(f"✓ ({metrics['output_tokens']} tok, quality: {validation['quality_score']:.2f})")

            variant_results['outputs'].append(output)
            variant_results['metrics'].append(metrics)
            variant_results['validations'].append({
                **validation,
                'coverage': coverage
            })

        # Aggregate metrics
        avg_output_tokens = sum(m['output_tokens'] for m in variant_results['metrics']) / len(turns)
        avg_quality = sum(v['quality_score'] for v in variant_results['validations']) / len(turns)
        avg_coverage = sum(v['coverage']['overall'] for v in variant_results['validations']) / len(turns)
        avg_hallucination = sum(v['hallucination_rate'] for v in variant_results['validations']) / len(turns)

        variant_results['aggregates'] = {
            'avg_output_tokens': avg_output_tokens,
            'avg_quality_score': avg_quality,
            'avg_coverage': avg_coverage,
            'avg_hallucination_rate': avg_hallucination
        }

        results[variant.name] = variant_results

        print(f"  Summary: {avg_output_tokens:.1f} tokens, quality {avg_quality:.2f}, coverage {avg_coverage:.2%}")
        print()

    # === Results Summary ===
    print("=" * 70)
    print("RESULTS SUMMARY")
    print("=" * 70)
    print()

    # Sort by quality score (descending)
    sorted_variants = sorted(
        results.items(),
        key=lambda x: x[1]['aggregates']['avg_quality_score'],
        reverse=True
    )

    print(f"{'Variant':<15} {'Tokens':>8} {'Quality':>10} {'Coverage':>10} {'Halluc':>10}")
    print("-" * 70)

    baseline_tokens = results['baseline']['aggregates']['avg_output_tokens']

    for name, data in sorted_variants:
        agg = data['aggregates']
        tokens = agg['avg_output_tokens']
        savings = ((baseline_tokens - tokens) / baseline_tokens) * 100

        marker = ""
        if name != 'baseline':
            marker = f" ({savings:+.0f}%)"

        print(f"{name:<15} {tokens:>8.1f}{marker:>10} {agg['avg_quality_score']:>10.2f} "
              f"{agg['avg_coverage']:>10.2%} {agg['avg_hallucination_rate']:>10.2%}")

    print()

    # Find winner
    print("=" * 70)
    print("WINNER ANALYSIS")
    print("=" * 70)
    print()

    # Filter candidates: quality >= 0.7, coverage >= 70%, hallucination <= 10%
    candidates = [
        (name, data) for name, data in results.items()
        if (data['aggregates']['avg_quality_score'] >= 0.7 and
            data['aggregates']['avg_coverage'] >= 0.7 and
            data['aggregates']['avg_hallucination_rate'] <= 0.1)
    ]

    if candidates:
        # Sort by token count (ascending) - most compressed
        winner_name, winner_data = min(candidates, key=lambda x: x[1]['aggregates']['avg_output_tokens'])

        print(f"Winner: {winner_name}")
        print(f"  Description: {winner_data['description']}")
        print(f"  Avg tokens: {winner_data['aggregates']['avg_output_tokens']:.1f}")
        print(f"  Quality score: {winner_data['aggregates']['avg_quality_score']:.2f}")
        print(f"  Coverage: {winner_data['aggregates']['avg_coverage']:.2%}")
        print()

        token_reduction = ((baseline_tokens - winner_data['aggregates']['avg_output_tokens']) / baseline_tokens) * 100
        print(f"Token reduction vs baseline: {token_reduction:.1f}%")
        print()

        # Example output
        print("Example output:")
        print("-" * 70)
        print(winner_data['outputs'][0][:300])
        print()
    else:
        print("! No variant met quality thresholds")
        print("  (quality >= 0.7, coverage >= 70%, hallucination <= 10%)")
        print()
        print("Best quality variant:")
        best_name, best_data = sorted_variants[0]
        print(f"  {best_name}: {best_data['aggregates']['avg_quality_score']:.2f}")

    # Save results
    logger = ResultsLogger(Path(__file__).parent.parent / "results")
    logger.log("arm_d_budget", {
        'turns_tested': len(turns),
        'variants': results,
        'winner': winner_name if candidates else None
    })

    print()
    print("✓ Results saved to arms/results/arm_d_budget_results.json")
    print()

    # === Recommendations ===
    print("=" * 70)
    print("RECOMMENDATIONS")
    print("=" * 70)
    print()

    if candidates:
        print(f"✓ ADOPT {winner_name} prompt variant")
        print()
        print("Integration steps:")
        print("  1. Update NANOBOT_ANE_PROMPTS.md with winning prompt")
        print("  2. Update service.py to use new prompt format")
        print(f"  3. Expected savings: {token_reduction:.0f}% fewer output tokens")
        print()
        print(f"AMD finding: Output tokens cost ~39x input tokens")
        print(f"If ANE shows similar ratio, expect ~{token_reduction * 39 / 100:.0f}x speedup")
    else:
        print("! No clear winner - all variants have quality issues")
        print("  Consider:")
        print("  - Improving base prompts")
        print("  - Using hybrid approach (combine strategies)")
        print("  - Accepting current token count")

    print()


def main():
    parser = argparse.ArgumentParser(description="ARM D: Token Budgeting")
    parser.add_argument(
        "--model",
        type=str,
        default="~/.nanobot/models/qwen3-1.7b/qwen3-ane-instruct.mlmodelc",
        help="Path to CoreML model"
    )
    parser.add_argument(
        "--quick",
        action="store_true",
        help="Run abbreviated tests (5 turns)"
    )

    args = parser.parse_args()

    model_path = Path(args.model).expanduser()

    if not model_path.exists():
        print(f"Error: Model not found at {model_path}")
        sys.exit(1)

    run_arm_d(str(model_path), quick=args.quick)


if __name__ == "__main__":
    main()
