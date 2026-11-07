#!/usr/bin/env python3
"""
Test chunk-size=2 + Budget 100 combination on real nanobot conversations.

Goal: Determine if chunking improves Budget 100's quality score (currently 0.62).

Tests three configurations:
1. Baseline: Per-turn extraction, no budget constraint
2. Budget 100: Per-turn extraction, ≤100 token budget
3. Chunk2+Budget100: 2-turn windows, ≤100 token budget per turn

Measures quality score using OutputValidator to see if chunking helps.
"""
import sys
import asyncio
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from ane_inference import ANEInference
from arms.shared import TokenCounter
from validator import OutputValidator, FactCoverageChecker


class CombinedExtractor:
    """Test baseline, Budget 100, and Chunk2+Budget100"""

    def __init__(self, model_path: str):
        self.inference = ANEInference(model_path)
        self.token_counter = TokenCounter()

    def extract_baseline(self, turns: list[dict]) -> tuple[str, dict]:
        """Baseline: per-turn, no budget constraint"""
        all_facts = []
        total_tokens = 0

        for turn in turns:
            turn_text = f"User: {turn['user']}\nAssistant: {turn['assistant']}"

            prompt = f"""Extract facts from this conversation turn. Be concise and specific.

Turn:
{turn_text}

Facts:"""

            output = asyncio.run(self.inference.generate(
                prompt=prompt,
                max_tokens=200,
                temperature=0.0
            ))

            all_facts.append(output)
            total_tokens += self.token_counter.count(output)

        return '\n\n'.join(all_facts), {
            'variant': 'baseline',
            'total_tokens': total_tokens,
            'avg_per_turn': total_tokens / len(turns) if turns else 0
        }

    def extract_budget100(self, turns: list[dict]) -> tuple[str, dict]:
        """Budget 100: per-turn, ≤100 token budget"""
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
                max_tokens=120,
                temperature=0.0
            ))

            all_facts.append(output)
            total_tokens += self.token_counter.count(output)

        return '\n\n'.join(all_facts), {
            'variant': 'budget100',
            'total_tokens': total_tokens,
            'avg_per_turn': total_tokens / len(turns) if turns else 0
        }

    def extract_chunk2_budget100(self, turns: list[dict]) -> tuple[str, dict]:
        """Chunk2+Budget100: 2-turn windows, ≤100 token budget per turn"""
        all_facts = []
        total_tokens = 0
        chunk_size = 2

        for i in range(0, len(turns), chunk_size):
            chunk_turns = turns[i:i+chunk_size]

            # Build chunk text
            chunk_text = []
            for j, turn in enumerate(chunk_turns):
                chunk_text.append(f"Turn {i+j+1}:")
                chunk_text.append(f"User: {turn['user']}")
                chunk_text.append(f"Assistant: {turn['assistant']}")
                chunk_text.append("")

            combined_text = '\n'.join(chunk_text)

            # Budget scales with chunk size
            target_tokens = 100 * len(chunk_turns)
            max_tokens = int(target_tokens * 1.2)

            prompt = f"""Extract facts from these {len(chunk_turns)} conversation turns. Target ≤{target_tokens} tokens total.
Be concise but clear. Abbreviate where unambiguous.
Preserve: numbers, percentages, file paths, specific names, measurements.

Turns:
{combined_text}

Facts (≤{target_tokens} tokens):"""

            output = asyncio.run(self.inference.generate(
                prompt=prompt,
                max_tokens=max_tokens,
                temperature=0.0
            ))

            all_facts.append(output)
            total_tokens += self.token_counter.count(output)

        # Calculate effective per-turn average
        avg_per_turn = total_tokens / len(turns) if turns else 0

        return '\n\n'.join(all_facts), {
            'variant': 'chunk2_budget100',
            'total_tokens': total_tokens,
            'avg_per_turn': avg_per_turn,
            'num_chunks': (len(turns) + chunk_size - 1) // chunk_size
        }


def load_nanobot_conversation(jsonl_path: str, max_turns: int = 10):
    """Load nanobot conversation from JSONL"""
    messages = []

    with open(jsonl_path, 'r') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue

            try:
                msg = json.loads(line)
                role = msg.get('role')
                content = msg.get('content', '')

                if role in ('user', 'assistant'):
                    messages.append({'role': role, 'content': content})
            except json.JSONDecodeError:
                continue

    # Extract turns (user + assistant pairs)
    turns = []
    for i in range(0, len(messages) - 1, 2):
        if messages[i]['role'] == 'user' and messages[i+1]['role'] == 'assistant':
            turn_text = f"User: {messages[i]['content']}\nAssistant: {messages[i+1]['content']}"
            turns.append({
                'user': messages[i]['content'],
                'assistant': messages[i+1]['content'],
                'turn_text': turn_text
            })

            if len(turns) >= max_turns:
                break

    return turns


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Test Chunk2 + Budget 100 combination on real conversations"
    )
    parser.add_argument(
        "--model",
        type=str,
        default="/Users/agundez/Build/Anemll/models/qwen3-1.7b-ctx2048",
        help="Path to model"
    )
    parser.add_argument(
        "--conversation",
        type=str,
        help="Path to nanobot conversation JSONL file"
    )
    parser.add_argument(
        "--turns",
        type=int,
        default=5,
        help="Number of turns to test (default: 5)"
    )

    args = parser.parse_args()

    # Find a conversation if not specified
    if not args.conversation:
        sessions_dir = Path.home() / ".nanobot" / "sessions"
        user_session = next(sessions_dir.glob("*"), None)
        if user_session:
            conversations = list(user_session.glob("*.jsonl"))
            if conversations:
                # Pick a mid-sized one
                conversations.sort(key=lambda p: p.stat().st_size)
                args.conversation = str(conversations[len(conversations) // 2])

    if not args.conversation:
        print("Error: No conversation found. Specify with --conversation")
        sys.exit(1)

    print("=" * 70)
    print("CHUNK2 + BUDGET 100 COMBINATION TEST")
    print("=" * 70)
    print()
    print(f"Model: {args.model}")
    print(f"Conversation: {Path(args.conversation).name}")
    print(f"Testing: {args.turns} turns")
    print()

    # Load conversation
    turns = load_nanobot_conversation(args.conversation, max_turns=args.turns)
    print(f"Loaded {len(turns)} turns from conversation")
    print()

    # Initialize extractor and validators
    extractor = CombinedExtractor(args.model)
    validator = OutputValidator()
    coverage_checker = FactCoverageChecker()

    # Test all three variants
    variants = [
        ('baseline', extractor.extract_baseline),
        ('budget100', extractor.extract_budget100),
        ('chunk2_budget100', extractor.extract_chunk2_budget100),
    ]

    results = []

    for variant_name, extract_func in variants:
        print(f"Testing {variant_name}...")

        extracted, metrics = extract_func(turns)

        # Validate quality on each turn
        turn_validations = []
        for turn in turns:
            validation = validator.validate(extracted, turn['turn_text'])
            coverage = coverage_checker.check_coverage(extracted, turn['turn_text'])
            turn_validations.append({
                'validation': validation,
                'coverage': coverage
            })

        # Aggregate quality scores
        avg_quality = sum(v['validation']['quality_score'] for v in turn_validations) / len(turns)
        avg_hallucination = sum(v['validation']['hallucination_rate'] for v in turn_validations) / len(turns)
        avg_coverage = sum(v['coverage']['overall'] for v in turn_validations) / len(turns)

        result = {
            'variant': variant_name,
            'metrics': metrics,
            'quality': avg_quality,
            'hallucination_rate': avg_hallucination,
            'coverage': avg_coverage,
            'extracted': extracted
        }

        results.append(result)

        print(f"  Total tokens: {metrics['total_tokens']}")
        print(f"  Avg per turn: {metrics['avg_per_turn']:.1f}")
        print(f"  Quality: {avg_quality:.2f}")
        print(f"  Hallucination: {avg_hallucination:.1%}")
        print(f"  Coverage: {avg_coverage:.1%}")
        print()

    # Summary comparison
    print("=" * 70)
    print("RESULTS SUMMARY")
    print("=" * 70)
    print()
    print(f"{'Variant':<20} {'Tokens':>10} {'Per-Turn':>10} {'Quality':>10} {'Halluc':>10} {'Savings':>10}")
    print("-" * 70)

    baseline = results[0]
    for r in results:
        savings = 100 * (baseline['metrics']['total_tokens'] - r['metrics']['total_tokens']) / baseline['metrics']['total_tokens']
        print(f"{r['variant']:<20} {r['metrics']['total_tokens']:>10} "
              f"{r['metrics']['avg_per_turn']:>10.1f} {r['quality']:>10.2f} "
              f"{r['hallucination_rate']:>9.1%} {savings:>9.1f}%")

    print()
    print("=" * 70)
    print("QUALITY ANALYSIS")
    print("=" * 70)
    print()

    budget100 = results[1]
    chunk2_budget100 = results[2]

    quality_change = chunk2_budget100['quality'] - budget100['quality']
    quality_change_pct = 100 * quality_change / budget100['quality'] if budget100['quality'] > 0 else 0

    print(f"Budget 100 quality: {budget100['quality']:.2f}")
    print(f"Chunk2+Budget100 quality: {chunk2_budget100['quality']:.2f}")
    print()
    print(f"Quality change: {quality_change:+.2f} ({quality_change_pct:+.1f}%)")
    print()

    if quality_change > 0.05:  # Meaningful improvement
        print(f"✓ Chunking IMPROVES Budget 100 quality by {quality_change:.2f}")
        print(f"  Recommendation: Adopt Chunk2+Budget100 combination")
    elif quality_change < -0.05:  # Meaningful degradation
        print(f"✗ Chunking DEGRADES Budget 100 quality by {-quality_change:.2f}")
        print(f"  Recommendation: Keep Budget 100 alone, use chunk2 separately")
    else:
        print(f"≈ Chunking has MINIMAL impact on Budget 100 quality")
        print(f"  Recommendation: Choose based on token savings preference")

    print()

    # Compare to baseline quality
    baseline_quality = baseline['quality']
    chunk2_budget100_vs_baseline = chunk2_budget100['quality'] - baseline_quality

    print(f"Baseline quality: {baseline_quality:.2f}")
    print(f"Chunk2+Budget100 vs Baseline: {chunk2_budget100_vs_baseline:+.2f}")
    print()

    if chunk2_budget100['quality'] >= 0.70:
        print(f"✓ Chunk2+Budget100 meets quality target (≥0.70)")
    elif chunk2_budget100['quality'] >= baseline_quality * 0.9:
        print(f"≈ Chunk2+Budget100 within 10% of baseline quality (acceptable)")
    else:
        print(f"⚠ Chunk2+Budget100 quality significantly below baseline")

    print()


if __name__ == "__main__":
    main()
