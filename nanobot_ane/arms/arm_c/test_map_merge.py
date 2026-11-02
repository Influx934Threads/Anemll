#!/usr/bin/env python3
"""
ARM C: Map-Mechanical-Merge Pattern

Tests whether CPU-side mechanical merging can replace LLM consolidation.
"""
import sys
from pathlib import Path
import argparse
import time
import asyncio

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from mechanical_merger import MechanicalMerger, EntityDeduplicator
from structured_extractor import StructuredFactExtractor
from ane_inference import ANEInference
from arms.shared import (
    Fixtures,
    ResultsLogger,
    TokenCounter,
    PromptTemplates
)


def run_baseline_llm_consolidation(inference, facts_text: str) -> tuple[str, dict]:
    """
    Baseline: Current LLM consolidation approach

    Takes facts and runs them through LLM to get coherent summary.
    """
    prompt = PromptTemplates.CONSOLIDATION_BASELINE.format(
        facts_text=facts_text
    )

    token_counter = TokenCounter()
    input_tokens = token_counter.count(prompt)

    start_time = time.time()
    output = asyncio.run(inference.generate(
        prompt=prompt,
        max_tokens=150,  # Target: <75 words = ~100 tokens
        temperature=0.0
    ))
    elapsed_ms = (time.time() - start_time) * 1000

    output_tokens = token_counter.count(output)

    metrics = {
        'input_tokens': input_tokens,
        'output_tokens': output_tokens,
        'time_ms': elapsed_ms,
        'method': 'llm_consolidation'
    }

    return output, metrics


def run_mechanical_merge(facts: list[dict]) -> tuple[str, dict]:
    """
    Test: Mechanical merge (zero-LLM)

    Takes structured facts and merges them without LLM.
    """
    merger = MechanicalMerger(similarity_threshold=0.85)

    start_time = time.time()
    result = merger.merge(facts)
    elapsed_ms = (time.time() - start_time) * 1000

    metrics = {
        'input_facts': len(facts),
        'output_facts': result['num_unique_facts'],
        'duplicates_removed': result['duplicate_count'],
        'compression_ratio': result['compression_ratio'],
        'time_ms': elapsed_ms,
        'method': 'mechanical_merge'
    }

    return result['text'], metrics


def evaluate_quality(summary: str, ground_truth_facts: list[dict]) -> dict:
    """
    Evaluate summary quality

    Check if key facts are preserved in the summary.
    """
    preserved_count = 0
    total_facts = len(ground_truth_facts)

    summary_lower = summary.lower()

    for fact in ground_truth_facts:
        content = fact.get('content', '').lower()

        # Check if core content appears in summary
        # (Simple heuristic: check if key words appear)
        key_words = [w for w in content.split() if len(w) > 4]

        if any(word in summary_lower for word in key_words[:3]):
            preserved_count += 1

    recall = preserved_count / total_facts if total_facts > 0 else 0

    return {
        'facts_preserved': preserved_count,
        'total_facts': total_facts,
        'recall': recall
    }


def run_arm_c(model_path: str, quick: bool = False):
    """Run ARM C map-mechanical-merge tests"""
    print("=" * 70)
    print("ARM C: Map-Mechanical-Merge Pattern")
    print("=" * 70)
    print()
    print("Goal: Replace LLM consolidation with mechanical CPU merging")
    print("Hypothesis: Mechanical merge saves time without losing quality")
    print()

    # Initialize components
    inference = ANEInference(model_path)
    extractor = StructuredFactExtractor(model_path)
    fixtures = Fixtures()

    # Load test conversation
    conversation = fixtures.get_conversation("small" if quick else "medium")

    print(f"Test conversation: {len(conversation)} messages")
    print()

    # Prepare turns
    turns = []
    for i in range(0, len(conversation), 2):
        if i + 1 < len(conversation):
            turn_text = f"User: {conversation[i]['content']}\nAssistant: {conversation[i+1]['content']}"
            turns.append(turn_text)

    if quick:
        turns = turns[:5]  # Test with 5 turns

    print(f"Testing with {len(turns)} turns")
    print()

    # === Phase 1: Extract facts from all turns ===
    print("Phase 1: Extracting facts from turns...")
    print("-" * 70)

    all_facts = []
    extraction_time = 0

    for i, turn in enumerate(turns):
        print(f"Turn {i+1}/{len(turns)}...", end=" ")
        facts, metrics = extractor.extract_facts(turn)
        extraction_time += metrics.get('time_ms', 0)
        all_facts.extend(facts)
        print(f"✓ ({len(facts)} facts, {metrics['output_tokens']} tokens)")

    print()
    print(f"Total facts extracted: {len(all_facts)}")
    print(f"Total extraction time: {extraction_time:.0f}ms")
    print()

    # === Phase 2: Baseline LLM consolidation ===
    print("Phase 2: Baseline LLM consolidation...")
    print("-" * 70)

    # Format facts as text for LLM
    facts_text = '\n'.join([f"- {fact['content']}" for fact in all_facts])

    baseline_summary, baseline_metrics = run_baseline_llm_consolidation(
        inference, facts_text
    )

    print(f"✓ LLM consolidation complete")
    print(f"  Time: {baseline_metrics['time_ms']:.0f}ms")
    print(f"  Output: {baseline_metrics['output_tokens']} tokens")
    print()
    print("Summary:")
    print(baseline_summary)
    print()

    # === Phase 3: Mechanical merge ===
    print("Phase 3: Mechanical merge (zero-LLM)...")
    print("-" * 70)

    mechanical_summary, mechanical_metrics = run_mechanical_merge(all_facts)

    print(f"✓ Mechanical merge complete")
    print(f"  Time: {mechanical_metrics['time_ms']:.0f}ms")
    print(f"  Duplicates removed: {mechanical_metrics['duplicates_removed']}")
    print(f"  Compression: {mechanical_metrics['compression_ratio']:.1f}x")
    print()
    print("Summary:")
    print(mechanical_summary)
    print()

    # === Phase 4: Quality evaluation ===
    print("Phase 4: Quality evaluation...")
    print("-" * 70)

    baseline_quality = evaluate_quality(baseline_summary, all_facts)
    mechanical_quality = evaluate_quality(mechanical_summary, all_facts)

    print(f"Baseline recall: {baseline_quality['recall']:.2%}")
    print(f"Mechanical recall: {mechanical_quality['recall']:.2%}")
    print()

    # === Results Summary ===
    print("=" * 70)
    print("RESULTS SUMMARY")
    print("=" * 70)
    print()

    total_baseline_time = extraction_time + baseline_metrics['time_ms']
    total_mechanical_time = extraction_time + mechanical_metrics['time_ms']

    print(f"{'Approach':<20} {'Time (ms)':>12} {'Recall':>10} {'Output Tokens':>15}")
    print("-" * 70)
    print(f"{'LLM Consolidation':<20} {total_baseline_time:>12.0f} {baseline_quality['recall']:>10.2%} "
          f"{baseline_metrics['output_tokens']:>15}")
    print(f"{'Mechanical Merge':<20} {total_mechanical_time:>12.0f} {mechanical_quality['recall']:>10.2%} "
          f"{'0 (CPU only)':>15}")
    print()

    time_savings = ((total_baseline_time - total_mechanical_time) / total_baseline_time) * 100
    print(f"Time savings: {time_savings:.1f}%")
    print()

    # Save results
    logger = ResultsLogger(Path(__file__).parent.parent / "results")
    logger.log("arm_c_merge", {
        'turns': len(turns),
        'total_facts': len(all_facts),
        'extraction_time_ms': extraction_time,
        'baseline': {
            'summary': baseline_summary,
            'metrics': baseline_metrics,
            'quality': baseline_quality,
            'total_time_ms': total_baseline_time
        },
        'mechanical': {
            'summary': mechanical_summary,
            'metrics': mechanical_metrics,
            'quality': mechanical_quality,
            'total_time_ms': total_mechanical_time
        },
        'time_savings_pct': time_savings
    })

    print("✓ Results saved to arms/results/arm_c_merge_results.json")
    print()

    # === Recommendations ===
    print("=" * 70)
    print("RECOMMENDATIONS")
    print("=" * 70)
    print()

    recall_diff = mechanical_quality['recall'] - baseline_quality['recall']

    if time_savings > 20 and recall_diff > -0.1:
        print("✓ MECHANICAL MERGE WINS")
        print(f"  - Time savings: {time_savings:.1f}%")
        print(f"  - Recall: {mechanical_quality['recall']:.2%} (vs {baseline_quality['recall']:.2%})")
        print(f"  - Recommendation: ADOPT mechanical merge")
        print()
        print("  Integration steps:")
        print("  1. Replace consolidation in service.py with MechanicalMerger")
        print("  2. Update prompts to use STRUCTURED_FACT_EXTRACTION")
        print("  3. Remove consolidation LLM call every 5 turns")
    elif recall_diff < -0.15:
        print("✗ QUALITY LOSS TOO HIGH")
        print(f"  - Recall drop: {recall_diff:.2%}")
        print(f"  - Time savings: {time_savings:.1f}%")
        print(f"  - Recommendation: KEEP LLM consolidation")
    else:
        print("~ MIXED RESULTS")
        print(f"  - Time savings: {time_savings:.1f}%")
        print(f"  - Recall change: {recall_diff:+.2%}")
        print(f"  - Consider hybrid approach")

    print()
    print("AMD NPU finding:")
    print("  - Reduce (2nd LLM pass) never beat 5/8 recall")
    print("  - Was non-monotonic (better input → worse output)")
    print("  - Mechanical merge avoids this failure mode")
    print()


def main():
    parser = argparse.ArgumentParser(description="ARM C: Map-Mechanical-Merge")
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

    run_arm_c(str(model_path), quick=args.quick)


if __name__ == "__main__":
    main()
