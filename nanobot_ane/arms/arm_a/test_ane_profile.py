#!/usr/bin/env python3
"""
ARM A: ANE Characteristics Profiling

Tests prefill vs decode performance to determine cost asymmetry
similar to AMD NPU's 39x ratio.
"""
import sys
from pathlib import Path
import argparse

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from profiler import ANEProfiler
from arms.shared import ResultsLogger


def run_arm_a(model_path: str, quick: bool = False):
    """
    Run ARM A profiling tests

    Args:
        model_path: Path to CoreML model
        quick: If True, run abbreviated test matrix
    """
    print("=" * 70)
    print("ARM A: ANE Characteristics Profiling")
    print("=" * 70)
    print()
    print("Goal: Measure prefill vs decode performance")
    print("Expected: Find ANE's cost asymmetry ratio (like AMD's 39x)")
    print()

    # Initialize profiler
    profiler = ANEProfiler(model_path)

    # Define test matrix (respecting model's 2048 context length)
    if quick:
        print("Running QUICK test matrix (reduced iterations)...")
        input_sizes = [256, 512, 1024]
        output_sizes = [50, 200]
        iterations = 2
    else:
        print("Running FULL test matrix...")
        input_sizes = [256, 512, 1024, 1536, 2000]
        output_sizes = [10, 50, 100, 200, 500]
        iterations = 5

    print(f"Input sizes: {input_sizes}")
    print(f"Output sizes: {output_sizes}")
    print(f"Iterations per config: {iterations}")
    print(f"Total tests: {len(input_sizes) * len(output_sizes) * iterations}")
    print()

    # Run benchmark
    print("Starting benchmark...")
    print("-" * 70)

    results = profiler.benchmark_scaling(
        input_sizes=input_sizes,
        output_sizes=output_sizes,
        iterations=iterations
    )

    # Print summary
    print()
    print("=" * 70)
    print("RESULTS SUMMARY")
    print("=" * 70)
    print()

    summary = results['summary']

    print(f"Average Prefill Speed:  {summary['avg_prefill_tok_per_sec']:.1f} tok/s")
    print(f"Average Decode Speed:   {summary['avg_decode_tok_per_sec']:.1f} tok/s")
    print(f"Cost Ratio (output/input): {summary['avg_cost_ratio']:.1f}x")
    print()
    print("Comparison to AMD NPU:")
    print(f"  AMD XDNA2:  39.0x (550 tok/s prefill, 14 tok/s decode)")
    print(f"  Apple ANE:  {summary['avg_cost_ratio']:.1f}x")
    print(f"  Difference: {summary['comparison_to_amd_npu']['ratio_difference']:+.1f}x")
    print()
    print(f"Time Prediction Accuracy: {summary['avg_prediction_error_pct']:.1f}% error")
    print()

    # Detailed results table
    print("=" * 70)
    print("DETAILED RESULTS")
    print("=" * 70)
    print()
    print(f"{'Input':>8} {'Output':>8} {'Total(ms)':>10} {'Prefill':>10} {'Decode':>10} {'Ratio':>8}")
    print("-" * 70)

    for result in results['test_matrix']:
        m = result['avg_metrics']
        print(f"{result['input_size']:>8} {result['output_size']:>8} "
              f"{m['total_time_ms']:>10.1f} {m['prefill_tok_per_sec']:>10.1f} "
              f"{m['decode_tok_per_sec']:>10.1f} {m['cost_ratio']:>8.1f}x")

    print()

    # Save results
    logger = ResultsLogger(Path(__file__).parent.parent / "results")
    logger.log("arm_a_profile", results)

    print()
    print("✓ Results saved to arms/results/arm_a_profile_results.json")
    print()

    # Recommendations
    print("=" * 70)
    print("RECOMMENDATIONS")
    print("=" * 70)
    print()

    ratio = summary['avg_cost_ratio']

    if ratio > 10:
        print("✓ ANE shows significant prefill advantage (>10x)")
        print("  → Optimize for MINIMIZING OUTPUT TOKENS")
        print("  → Reading context is cheap, writing is expensive")
        print("  → Apply AMD NPU learnings:")
        print("    - Bounded output (<300 tokens)")
        print("    - Single-pass operations")
        print("    - Avoid output scaling with input")
    elif ratio > 5:
        print("✓ ANE shows moderate prefill advantage (5-10x)")
        print("  → Output token optimization will help but not critical")
        print("  → Some AMD learnings apply with lower priority")
    else:
        print("! ANE does NOT show strong prefill advantage (<5x)")
        print("  → AMD NPU learnings may not transfer directly")
        print("  → Different optimization strategy needed")

    print()
    print("Next steps:")
    print("  1. Review detailed results in arms/results/arm_a_profile_results.json")
    print("  2. Run analysis script: python arms/arm_a/analyze_results.py")
    print("  3. If ratio >10x, proceed to ARM B, C, D (output optimization)")
    print("  4. If ratio <5x, revisit strategy before other arms")
    print()


def main():
    parser = argparse.ArgumentParser(description="ARM A: ANE Profiling")
    parser.add_argument(
        "--model",
        type=str,
        default="~/.nanobot/models/qwen3-1.7b/qwen3-ane-instruct.mlmodelc",
        help="Path to CoreML model"
    )
    parser.add_argument(
        "--quick",
        action="store_true",
        help="Run abbreviated test matrix for quick results"
    )

    args = parser.parse_args()

    model_path = Path(args.model).expanduser()

    if not model_path.exists():
        print(f"Error: Model not found at {model_path}")
        print()
        print("Please specify correct path with --model flag")
        sys.exit(1)

    run_arm_a(str(model_path), quick=args.quick)


if __name__ == "__main__":
    main()
