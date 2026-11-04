#!/usr/bin/env python3
"""
Tune d1_strict to find optimal quality/cost trade-off.

Tests different token budgets to find the sweet spot between
baseline (251 tokens, 0.72 quality) and d1_strict (58 tokens, 0.62 quality).
"""
import sys
import asyncio
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from ane_inference import ANEInference
from arms.shared import TokenCounter, Fixtures
from validator import OutputValidator, FactCoverageChecker


class TunedVariant:
    """Tuned d1_strict variant with adjustable parameters"""

    def __init__(self, model_path: str, max_tokens: int, concision_level: str,
                 preserve_details: bool = False):
        self.inference = ANEInference(model_path)
        self.token_counter = TokenCounter()
        self.max_tokens = max_tokens
        self.concision_level = concision_level
        self.preserve_details = preserve_details
        self.name = f"d1_tuned_{max_tokens}"

    def extract_facts(self, turn_text: str) -> tuple[str, dict]:
        """Extract facts with tuned parameters"""

        # Build prompt based on settings
        if self.concision_level == "extreme":
            concision_instruction = "Use extreme concision. Omit articles, use abbreviations."
        elif self.concision_level == "moderate":
            concision_instruction = "Be concise but clear. Abbreviate where unambiguous."
        else:  # "soft"
            concision_instruction = "Be brief but preserve important details."

        preserve_instruction = ""
        if self.preserve_details:
            preserve_instruction = "\nPreserve: numbers, percentages, file paths, specific names, measurements."

        prompt = f"""Extract facts from this conversation turn. Target ≤{self.max_tokens} tokens.
{concision_instruction}{preserve_instruction}

Turn:
{turn_text}

Facts (≤{self.max_tokens} tokens):"""

        input_tokens = self.token_counter.count(prompt)

        output = asyncio.run(self.inference.generate(
            prompt=prompt,
            max_tokens=self.max_tokens + 20,  # Small buffer
            temperature=0.0
        ))

        output_tokens = self.token_counter.count(output)

        metrics = {
            'variant': self.name,
            'input_tokens': input_tokens,
            'output_tokens': output_tokens,
            'max_tokens_target': self.max_tokens
        }

        return output, metrics


def run_tuning_test(model_path: str):
    """Run tuning test to find optimal d1_strict parameters"""

    print("=" * 70)
    print("D1_STRICT TUNING TEST")
    print("=" * 70)
    print()
    print("Goal: Find sweet spot between cost and quality")
    print("Baseline: 251 tokens, 0.72 quality")
    print("d1_strict: 58 tokens, 0.62 quality")
    print()

    # Initialize
    validator = OutputValidator()
    coverage_checker = FactCoverageChecker()
    fixtures = Fixtures()

    # Load test data (same 5 turns from ARM D)
    conversation = fixtures.get_conversation("small")
    turns = []
    for i in range(0, min(len(conversation), 10), 2):
        if i + 1 < len(conversation):
            turn_text = f"User: {conversation[i]['content']}\nAssistant: {conversation[i+1]['content']}"
            turns.append(turn_text)

    print(f"Testing on {len(turns)} turns")
    print()

    # Test configurations
    configs = [
        # (max_tokens, concision_level, preserve_details, description)
        (60, "extreme", False, "Budget 60, extreme concision"),
        (70, "extreme", False, "Budget 70, extreme concision"),
        (80, "moderate", False, "Budget 80, moderate concision"),
        (90, "moderate", True, "Budget 90, moderate + preserve details"),
        (100, "moderate", True, "Budget 100, moderate + preserve details"),
        (125, "soft", True, "Budget 125, soft + preserve details"),
    ]

    results = []

    for max_tokens, concision, preserve, desc in configs:
        print(f"Testing: {desc}")
        print("-" * 70)

        variant = TunedVariant(model_path, max_tokens, concision, preserve)

        turn_results = []
        for i, turn in enumerate(turns):
            output, metrics = variant.extract_facts(turn)

            # Validate
            validation = validator.validate(output, turn)
            coverage = coverage_checker.check_coverage(output, turn)

            turn_results.append({
                'output': output,
                'metrics': metrics,
                'validation': validation,
                'coverage': coverage
            })

            print(f"  Turn {i+1}/{len(turns)}: {metrics['output_tokens']} tok, "
                  f"quality {validation['quality_score']:.2f}")

        # Aggregate
        avg_tokens = sum(r['metrics']['output_tokens'] for r in turn_results) / len(turns)
        avg_quality = sum(r['validation']['quality_score'] for r in turn_results) / len(turns)
        avg_coverage = sum(r['coverage']['overall'] for r in turn_results) / len(turns)
        avg_halluc = sum(r['validation']['hallucination_rate'] for r in turn_results) / len(turns)

        results.append({
            'config': desc,
            'max_tokens': max_tokens,
            'avg_tokens': avg_tokens,
            'avg_quality': avg_quality,
            'avg_coverage': avg_coverage,
            'avg_hallucination': avg_halluc,
            'token_reduction': (251 - avg_tokens) / 251 * 100
        })

        print(f"  Avg: {avg_tokens:.1f} tokens, {avg_quality:.2f} quality, "
              f"{avg_halluc:.1%} hallucination")
        print()

    # Summary
    print("=" * 70)
    print("TUNING RESULTS SUMMARY")
    print("=" * 70)
    print()
    print(f"{'Config':<45} {'Tokens':>8} {'Quality':>8} {'Halluc':>8} {'Savings':>8}")
    print("-" * 70)
    print(f"{'BASELINE (reference)':<45} {'251.0':>8} {'0.72':>8} {'0%':>8} {'-':>8}")

    for r in results:
        print(f"{r['config']:<45} {r['avg_tokens']:>8.1f} {r['avg_quality']:>8.2f} "
              f"{r['avg_hallucination']:>7.1%} {r['token_reduction']:>7.1f}%")

    print()
    print("=" * 70)
    print("RECOMMENDATIONS")
    print("=" * 70)
    print()

    # Find best by quality target
    best_for_quality = None
    for r in results:
        if r['avg_quality'] >= 0.70 and r['avg_hallucination'] < 0.05:
            if best_for_quality is None or r['avg_tokens'] < best_for_quality['avg_tokens']:
                best_for_quality = r

    if best_for_quality:
        print(f"✓ Best quality/cost balance (≥0.70 quality, <5% hallucination):")
        print(f"  Config: {best_for_quality['config']}")
        print(f"  Tokens: {best_for_quality['avg_tokens']:.1f} (vs baseline 251)")
        print(f"  Quality: {best_for_quality['avg_quality']:.2f} (vs baseline 0.72)")
        print(f"  Savings: {best_for_quality['token_reduction']:.1f}%")
        print()
        print(f"  Integration: Update fact extraction prompt with:")
        print(f"    max_tokens={best_for_quality['max_tokens']}")
    else:
        print("⚠️  No configuration met quality target (≥0.70, <5% hallucination)")
        print("  Consider using baseline or accepting lower quality threshold")


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Tune d1_strict parameters for optimal quality/cost"
    )
    parser.add_argument(
        "--model",
        type=str,
        default="/Users/agundez/Build/Anemll/models/qwen3-1.7b-ctx2048",
        help="Path to model"
    )

    args = parser.parse_args()
    model_path = Path(args.model).expanduser()

    if not model_path.exists():
        print(f"Error: Model not found at {model_path}")
        sys.exit(1)

    run_tuning_test(str(model_path))


if __name__ == "__main__":
    main()
