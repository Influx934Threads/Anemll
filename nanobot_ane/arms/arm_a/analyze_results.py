#!/usr/bin/env python3
"""Analyze ARM A profiling results and generate report"""
import sys
from pathlib import Path
import json

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from arms.shared import ResultsLogger


def analyze_arm_a_results():
    """Load and analyze ARM A results"""
    logger = ResultsLogger(Path(__file__).parent.parent / "results")

    try:
        results = logger.load("arm_a_profile")
    except FileNotFoundError:
        print("Error: No results found. Run test_ane_profile.py first.")
        sys.exit(1)

    print("=" * 70)
    print("ARM A ANALYSIS")
    print("=" * 70)
    print()

    summary = results['summary']
    test_matrix = results['test_matrix']

    # === Finding 1: Cost Asymmetry ===
    print("## Finding 1: Cost Asymmetry (Prefill vs Decode)")
    print()
    cost_ratio = summary['avg_cost_ratio']
    print(f"**ANE Cost Ratio: {cost_ratio:.1f}x**")
    print(f"(Prefill: {summary['avg_prefill_tok_per_sec']:.1f} tok/s, "
          f"Decode: {summary['avg_decode_tok_per_sec']:.1f} tok/s)")
    print()

    amd_ratio = 39.0
    if abs(cost_ratio - amd_ratio) / amd_ratio < 0.2:
        print(f"✓ SIMILAR to AMD NPU ({amd_ratio:.0f}x)")
        print("  → AMD learnings transfer directly")
    elif cost_ratio > amd_ratio:
        print(f"✓ STRONGER than AMD NPU (+{cost_ratio - amd_ratio:.1f}x)")
        print("  → Output optimization even MORE critical")
    else:
        print(f"✗ WEAKER than AMD NPU ({cost_ratio - amd_ratio:.1f}x)")
        print("  → Output optimization less critical, but still valuable")

    print()

    # === Finding 2: Best-Fit Envelope ===
    print("## Finding 2: ANE Best-Fit Envelope")
    print()
    print("AMD NPU envelope: ≤8K in, ≤300 out, one pass")
    print()

    # Find configurations that work well (low prediction error)
    good_configs = [r for r in test_matrix
                    if r['avg_metrics']['prediction_error_pct'] < 10]

    if good_configs:
        max_input = max(r['input_size'] for r in good_configs)
        max_output = max(r['output_size'] for r in good_configs)
        print(f"ANE envelope (prediction error <10%): ≤{max_input} in, ≤{max_output} out")
    else:
        print("WARNING: No configurations achieved <10% prediction error")
        print("         Cost model may need refinement")

    print()

    # === Finding 3: Scaling Behavior ===
    print("## Finding 3: Scaling Behavior")
    print()

    # Group by output size, see how input affects time
    output_sizes = sorted(set(r['output_size'] for r in test_matrix))

    print("Input scaling (time vs input tokens, fixed output):")
    for output_size in output_sizes[:3]:  # Show first 3
        configs = [r for r in test_matrix if r['output_size'] == output_size]
        configs.sort(key=lambda x: x['input_size'])

        times = [r['avg_metrics']['total_time_ms'] for r in configs]
        inputs = [r['input_size'] for r in configs]

        if len(times) > 1:
            # Check if linear
            time_growth = times[-1] / times[0]
            input_growth = inputs[-1] / inputs[0]
            linearity = time_growth / input_growth

            print(f"  Output={output_size}: {times[0]:.0f}ms → {times[-1]:.0f}ms "
                  f"({input_growth:.1f}x input → {time_growth:.1f}x time, "
                  f"linearity={linearity:.2f})")

    print()

    # Group by input size, see how output affects time
    input_sizes = sorted(set(r['input_size'] for r in test_matrix))

    print("Output scaling (time vs output tokens, fixed input):")
    for input_size in input_sizes[:3]:  # Show first 3
        configs = [r for r in test_matrix if r['input_size'] == input_size]
        configs.sort(key=lambda x: x['output_size'])

        times = [r['avg_metrics']['total_time_ms'] for r in configs]
        outputs = [r['output_size'] for r in configs]

        if len(times) > 1:
            time_growth = times[-1] / times[0]
            output_growth = outputs[-1] / outputs[0]
            linearity = time_growth / output_growth

            print(f"  Input={input_size}: {times[0]:.0f}ms → {times[-1]:.0f}ms "
                  f"({output_growth:.1f}x output → {time_growth:.1f}x time, "
                  f"linearity={linearity:.2f})")

    print()

    # === Finding 4: Time Prediction Formula ===
    print("## Finding 4: Time Prediction Formula")
    print()
    print("Based on measured speeds:")
    print(f"  predicted_time = (input_tokens / {summary['avg_prefill_tok_per_sec']:.1f}) "
          f"+ (output_tokens / {summary['avg_decode_tok_per_sec']:.1f})")
    print()
    print(f"Average prediction error: {summary['avg_prediction_error_pct']:.1f}%")

    if summary['avg_prediction_error_pct'] < 5:
        print("✓ EXCELLENT accuracy (<5% error)")
    elif summary['avg_prediction_error_pct'] < 10:
        print("✓ GOOD accuracy (<10% error)")
    else:
        print("✗ POOR accuracy (>10% error) - model needs refinement")

    print()

    # === Recommendations ===
    print("=" * 70)
    print("RECOMMENDATIONS FOR OTHER ARMS")
    print("=" * 70)
    print()

    if cost_ratio > 10:
        print("ARM B (Generative Selection): **HIGH PRIORITY**")
        print("  - Output ~30 tokens vs ~100-150 tokens for fact extraction")
        print(f"  - Expected savings: ~{100 / 30 * cost_ratio:.0f}x faster")
        print()

        print("ARM C (Map-Mechanical-Merge): **HIGH PRIORITY**")
        print("  - Eliminate 2nd LLM pass (consolidation)")
        print(f"  - Save ~100 output tokens per consolidation")
        print()

        print("ARM D (Token Budgeting): **HIGH PRIORITY**")
        print("  - Reduce output from ~100-150 to ~50-60 tokens")
        print(f"  - Expected savings: ~{100 / 60:.1f}x faster per operation")

    elif cost_ratio > 5:
        print("ARM B, C, D: **MEDIUM PRIORITY**")
        print("  - Output optimization will help but not critical")

    else:
        print("ARM B, C, D: **LOW PRIORITY**")
        print("  - Output optimization less valuable on ANE")
        print("  - Consider different optimization strategies")

    print()

    # Generate markdown report
    report_path = Path(__file__).parent.parent / "results" / "arm_a_analysis.md"
    generate_markdown_report(results, report_path)

    print(f"✓ Detailed report saved to {report_path}")
    print()


def generate_markdown_report(results: dict, output_path: Path):
    """Generate markdown analysis report"""
    summary = results['summary']

    report = f"""# ARM A: ANE Characteristics Profiling - Analysis Report

## Executive Summary

**ANE Cost Ratio: {summary['avg_cost_ratio']:.1f}x** (prefill vs decode)

- Prefill Speed: {summary['avg_prefill_tok_per_sec']:.1f} tok/s
- Decode Speed: {summary['avg_decode_tok_per_sec']:.1f} tok/s
- Prediction Accuracy: {summary['avg_prediction_error_pct']:.1f}% average error

**Comparison to AMD NPU:**
- AMD XDNA2: 39.0x (550 tok/s prefill, 14 tok/s decode)
- Apple ANE: {summary['avg_cost_ratio']:.1f}x
- Difference: {summary['comparison_to_amd_npu']['ratio_difference']:+.1f}x

## Key Findings

### 1. Cost Asymmetry

{"ANE shows strong prefill advantage. Output tokens are the primary cost driver." if summary['avg_cost_ratio'] > 10 else "ANE shows moderate asymmetry. Both input and output matter."}

**Implication:** {"Optimize for minimizing output tokens, not input tokens." if summary['avg_cost_ratio'] > 10 else "Balance input and output optimization."}

### 2. Time Prediction Formula

```
predicted_time_ms = (input_tokens / {summary['avg_prefill_tok_per_sec']:.1f}) + (output_tokens / {summary['avg_decode_tok_per_sec']:.1f})
```

Accuracy: {summary['avg_prediction_error_pct']:.1f}% average error

### 3. Transferable Learnings from AMD Investigation

{"✓ APPLIES" if summary['avg_cost_ratio'] > 10 else "✗ LIMITED"} - Bounded output (<300 tokens)
{"✓ APPLIES" if summary['avg_cost_ratio'] > 10 else "✗ LIMITED"} - Single-pass operations
{"✓ APPLIES" if summary['avg_cost_ratio'] > 10 else "✗ LIMITED"} - Avoid output scaling with input
{"✓ APPLIES" if summary['avg_cost_ratio'] > 10 else "~ MAYBE"} - Generative selection over embeddings

## Detailed Results

| Input Tokens | Output Tokens | Total Time (ms) | Prefill (tok/s) | Decode (tok/s) | Ratio |
|--------------|---------------|-----------------|-----------------|----------------|-------|
"""

    for result in results['test_matrix']:
        m = result['avg_metrics']
        report += f"| {result['input_size']} | {result['output_size']} | {m['total_time_ms']:.1f} | {m['prefill_tok_per_sec']:.1f} | {m['decode_tok_per_sec']:.1f} | {m['cost_ratio']:.1f}x |\n"

    report += """
## Recommendations

### Next Steps

"""

    if summary['avg_cost_ratio'] > 10:
        report += """1. **HIGH PRIORITY:** Run ARM B, C, D (output token optimization)
2. Expected impact: Significant speedup from reducing output tokens
3. Apply AMD NPU learnings directly

### Expected Improvements

- ARM B (Generative Selection): ~3-5x faster than fact extraction
- ARM C (Mechanical Merge): ~30-40% time savings
- ARM D (Token Budgeting): ~40-50% token reduction
"""
    else:
        report += """1. **REASSESS:** AMD learnings may not transfer fully
2. Consider ANE-specific optimization strategies
3. Run ARM B, C, D at lower priority
"""

    report += f"""
## Metadata

- Test Date: {results.get('_metadata', {}).get('timestamp', 'unknown')}
- Total Configurations: {len(results['test_matrix'])}
"""

    output_path.write_text(report)


if __name__ == "__main__":
    analyze_arm_a_results()
