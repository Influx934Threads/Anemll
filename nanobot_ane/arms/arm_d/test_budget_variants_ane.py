#!/usr/bin/env python3
"""
Test different budget constraints on 4B ANE model with synthetic conversations.

Compares:
1. No budget (no token constraint)
2. Budget 100 (≤100 tokens per turn)
3. Budget 150 (≤150 tokens per turn)

Uses same synthetic conversation methodology as chunk-size tests to measure
recall of planted facts.
"""

import sys
import asyncio
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from ane_inference import ANEInference
from arms.shared import TokenCounter
from arms.arm_d.synthetic_fixtures import (
    generate_nanobot_conversation,
    score_recall,
    PlantedFact
)


class BudgetVariantExtractor:
    """Extract facts with different budget constraints using ANE model"""

    def __init__(self, model_path: str):
        self.inference = ANEInference(model_path)
        self.token_counter = TokenCounter()

    def extract_no_budget(self, turns: list[dict]) -> tuple[str, dict]:
        """Baseline: extract per turn with NO budget constraint"""
        all_facts = []
        total_tokens = 0

        for turn in turns:
            turn_text = f"User: {turn['user']}\nAssistant: {turn['assistant']}"

            prompt = f"""Extract facts from this conversation turn. Be concise but complete.
Preserve: numbers, percentages, file paths, specific names, measurements, user decisions.

Turn:
{turn_text}

Facts:"""

            output = asyncio.run(self.inference.generate(
                prompt=prompt,
                max_tokens=200,  # Generous limit, no explicit budget
                temperature=0.0
            ))

            all_facts.append(output)
            total_tokens += self.token_counter.count(output)

        return '\n\n'.join(all_facts), {
            'budget': 'none',
            'num_turns': len(turns),
            'total_tokens': total_tokens,
            'avg_per_turn': total_tokens / len(turns) if turns else 0
        }

    def extract_budget100(self, turns: list[dict]) -> tuple[str, dict]:
        """Budget 100: extract per turn with ≤100 token constraint"""
        all_facts = []
        total_tokens = 0

        for turn in turns:
            turn_text = f"User: {turn['user']}\nAssistant: {turn['assistant']}"

            prompt = f"""Extract facts from this conversation turn. Target ≤100 tokens.
Be concise but clear. Abbreviate where unambiguous.
Preserve: numbers, percentages, file paths, specific names, measurements.

Turn:
{turn_text}

Facts (≤100 tokens):"""

            output = asyncio.run(self.inference.generate(
                prompt=prompt,
                max_tokens=120,  # Small buffer
                temperature=0.0
            ))

            all_facts.append(output)
            total_tokens += self.token_counter.count(output)

        return '\n\n'.join(all_facts), {
            'budget': '100',
            'num_turns': len(turns),
            'total_tokens': total_tokens,
            'avg_per_turn': total_tokens / len(turns) if turns else 0
        }

    def extract_budget150(self, turns: list[dict]) -> tuple[str, dict]:
        """Budget 150: extract per turn with ≤150 token constraint"""
        all_facts = []
        total_tokens = 0

        for turn in turns:
            turn_text = f"User: {turn['user']}\nAssistant: {turn['assistant']}"

            prompt = f"""Extract facts from this conversation turn. Target ≤150 tokens.
Be concise but thorough. Abbreviate where unambiguous.
Preserve: numbers, percentages, file paths, specific names, measurements.

Turn:
{turn_text}

Facts (≤150 tokens):"""

            output = asyncio.run(self.inference.generate(
                prompt=prompt,
                max_tokens=180,  # Small buffer
                temperature=0.0
            ))

            all_facts.append(output)
            total_tokens += self.token_counter.count(output)

        return '\n\n'.join(all_facts), {
            'budget': '150',
            'num_turns': len(turns),
            'total_tokens': total_tokens,
            'avg_per_turn': total_tokens / len(turns) if turns else 0
        }


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Test budget variants on ANE model (4B)"
    )
    parser.add_argument(
        "--model",
        type=str,
        default="/Users/agundez/Build/Anemll/models/qwen3-4b-ctx2048",
        help="Path to ANE model (default: qwen3-4b-ctx2048)"
    )
    parser.add_argument(
        "--turns",
        type=int,
        default=48,
        help="Number of turns in synthetic conversation (default: 48)"
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=101,
        help="Random seed for synthetic generation (default: 101)"
    )
    parser.add_argument(
        "--budgets",
        type=str,
        default="none,100,150",
        help="Comma-separated budgets to test (default: none,100,150)"
    )

    args = parser.parse_args()

    # Parse budget list
    budgets = args.budgets.split(',')

    print("=" * 70)
    print("BUDGET VARIANT TEST (ANE 4B)")
    print("=" * 70)
    print()
    print(f"Model: {args.model.split('/')[-1]}")
    print(f"Synthetic turns: {args.turns}")
    print(f"Seed: {args.seed}")
    print(f"Budgets: {budgets}")
    print()

    # Generate synthetic conversation
    print("Generating synthetic conversation...")
    conversation, planted_facts = generate_nanobot_conversation(
        num_turns=args.turns,
        seed=args.seed
    )
    print(f"Generated {len(conversation)} turns with {len(planted_facts)} planted facts")
    print()

    # Show sample facts
    print("Sample planted facts:")
    for fact in planted_facts[:3]:
        print(f"  - {fact}")
    print()

    # Initialize extractor
    extractor = BudgetVariantExtractor(args.model)

    # Test each budget variant
    results = []

    for budget in budgets:
        print(f"Testing budget={budget}...")

        if budget == 'none':
            extracted, metrics = extractor.extract_no_budget(conversation)
        elif budget == '100':
            extracted, metrics = extractor.extract_budget100(conversation)
        elif budget == '150':
            extracted, metrics = extractor.extract_budget150(conversation)
        else:
            print(f"  Unknown budget: {budget}, skipping")
            continue

        # Score recall
        recalled, missed = score_recall(extracted, planted_facts)
        found = len(recalled)
        total = len(planted_facts)
        recall_pct = 100 * found / total if total > 0 else 0

        result = {
            'budget': budget,
            'metrics': metrics,
            'recall': {
                'found': found,
                'total': total,
                'recalled': recalled,
                'missed': missed
            }
        }
        results.append(result)

        print(f"  Turns: {metrics['num_turns']}")
        print(f"  Total tokens: {metrics['total_tokens']}")
        print(f"  Recall: {found}/{total} ({recall_pct:.1f}%)")

        # Show missed facts if any
        if missed:
            print(f"  Missed facts:")
            for fact in missed:
                print(f"    - {fact}")

        print()

    # Summary table
    print("=" * 70)
    print("RESULTS SUMMARY")
    print("=" * 70)
    print()
    print(f"{'Budget':<15} {'Turns':>8} {'Tokens':>10} {'Recall':>15} {'Savings':>10}")
    print("-" * 70)

    baseline = results[0]
    for r in results:
        budget_label = f"Budget {r['budget']}" if r['budget'] != 'none' else "No budget"
        found = r['recall']['found']
        total = r['recall']['total']
        recall_str = f"{found}/{total} ({100*found/total:.1f}%)"

        savings = 0
        if baseline['metrics']['total_tokens'] > 0:
            savings = 100 * (baseline['metrics']['total_tokens'] - r['metrics']['total_tokens']) / baseline['metrics']['total_tokens']

        print(f"{budget_label:<15} {r['metrics']['num_turns']:>8} "
              f"{r['metrics']['total_tokens']:>10} {recall_str:>15} {savings:>9.1f}%")

    print()

    # Analysis
    print("=" * 70)
    print("ANALYSIS")
    print("=" * 70)
    print()

    # Find best configuration
    best_recall = max(r['recall']['found'] / r['recall']['total'] for r in results)
    best_configs = [r for r in results if r['recall']['found'] / r['recall']['total'] == best_recall]

    if len(best_configs) == 1:
        best = best_configs[0]
        budget_label = f"Budget {best['budget']}" if best['budget'] != 'none' else "No budget"
        found = best['recall']['found']
        total = best['recall']['total']
        savings = 0
        if baseline['metrics']['total_tokens'] > 0:
            savings = 100 * (baseline['metrics']['total_tokens'] - best['metrics']['total_tokens']) / baseline['metrics']['total_tokens']

        print(f"✓ Best configuration: {budget_label}")
        print(f"  Token savings: {savings:.1f}% (baseline: {baseline['metrics']['total_tokens']} → {best['metrics']['total_tokens']})")
        print(f"  Recall: {found}/{total} ({100*found/total:.1f}%)")
        print(f"  Avg tokens per turn: {best['metrics']['avg_per_turn']:.1f}")
    else:
        print(f"✓ Multiple configurations achieve perfect recall:")
        for best in best_configs:
            budget_label = f"Budget {best['budget']}" if best['budget'] != 'none' else "No budget"
            found = best['recall']['found']
            total = best['recall']['total']
            print(f"  - {budget_label}: {found}/{total} ({100*found/total:.1f}%), {best['metrics']['total_tokens']} tokens")

    print()

    # Save results
    results_file = Path(__file__).parent.parent / "results" / f"budget_variants_ane_seed{args.seed}.json"
    results_file.parent.mkdir(parents=True, exist_ok=True)

    with open(results_file, 'w') as f:
        json.dump({
            'model': args.model.split('/')[-1],
            'seed': args.seed,
            'num_turns': args.turns,
            'planted_facts_count': len(planted_facts),
            'planted_facts': [str(f) for f in planted_facts],
            'results': [{
                'budget': r['budget'],
                'total_tokens': r['metrics']['total_tokens'],
                'avg_per_turn': r['metrics']['avg_per_turn'],
                'recall_found': r['recall']['found'],
                'recall_total': r['recall']['total'],
                'recall_percentage': 100 * r['recall']['found'] / r['recall']['total'],
                'missed_facts': [str(f) for f in r['recall']['missed']]
            } for r in results]
        }, f, indent=2)

    print(f"Results saved to: {results_file}")
    print()


if __name__ == "__main__":
    main()
