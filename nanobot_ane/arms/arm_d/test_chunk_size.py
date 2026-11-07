#!/usr/bin/env python3
"""
Test chunk-size optimization on synthetic nanobot conversations.

Based on AMD NPU finding: fewer, larger chunks amortize per-call overhead,
reducing total tokens by 59-71% with preserved recall (on 9B model + cue).

Tests on Bonsai 9B model (same size AMD validated) via port 8080.
"""

import sys
import requests
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from arms.shared import TokenCounter
from arms.arm_d.synthetic_fixtures import (
    generate_nanobot_conversation,
    score_recall,
    PlantedFact
)


class BonsaiInference:
    """Client for Bonsai 9B model on port 8080"""

    def __init__(self, base_url: str = "http://localhost:8080"):
        self.base_url = base_url

    def generate(self, prompt: str, max_tokens: int = 100, temperature: float = 0.0) -> str:
        """Generate completion from Bonsai model"""
        response = requests.post(
            f"{self.base_url}/v1/completions",
            json={
                "prompt": prompt,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "stop": ["\n\nUser:", "\n\nTurn"]
            },
            timeout=30
        )

        if response.status_code != 200:
            raise RuntimeError(f"Bonsai API error: {response.status_code} {response.text}")

        result = response.json()
        return result['choices'][0]['text'].strip()


class ChunkSizeExtractor:
    """Extract facts with different chunk sizes"""

    def __init__(self):
        self.inference = BonsaiInference()
        self.token_counter = TokenCounter()

    def extract_per_turn(self, turns: list[dict]) -> tuple[str, dict]:
        """Baseline: extract per turn (chunk_size=1)"""
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

            output = self.inference.generate(prompt, max_tokens=120, temperature=0.0)
            all_facts.append(output)
            total_tokens += self.token_counter.count(output)

        return '\n\n'.join(all_facts), {
            'chunk_size': 1,
            'num_chunks': len(turns),
            'total_tokens': total_tokens,
            'avg_per_chunk': total_tokens / len(turns) if turns else 0
        }

    def extract_chunked(
        self,
        turns: list[dict],
        chunk_size: int
    ) -> tuple[str, dict]:
        """Extract over N-turn windows"""
        all_facts = []
        total_tokens = 0
        num_chunks = 0

        for i in range(0, len(turns), chunk_size):
            chunk_turns = turns[i:i+chunk_size]

            # Combine turns in chunk
            chunk_text = []
            for j, turn in enumerate(chunk_turns):
                chunk_text.append(f"Turn {i+j+1}:")
                chunk_text.append(f"User: {turn['user']}")
                chunk_text.append(f"Assistant: {turn['assistant']}")
                chunk_text.append("")

            combined_text = '\n'.join(chunk_text)

            # Adaptive token budget based on chunk size
            target_tokens = 100 * len(chunk_turns)
            max_tokens = int(target_tokens * 1.2)  # 20% buffer

            prompt = f"""Extract facts from these {len(chunk_turns)} conversation turns. Target ≤{target_tokens} tokens.
Be concise but clear. Abbreviate where unambiguous.
Preserve: numbers, percentages, file paths, specific names, measurements.

Turns:
{combined_text}

Facts (≤{target_tokens} tokens):"""

            output = self.inference.generate(prompt, max_tokens=max_tokens, temperature=0.0)
            all_facts.append(output)
            total_tokens += self.token_counter.count(output)
            num_chunks += 1

        return '\n\n'.join(all_facts), {
            'chunk_size': chunk_size,
            'num_chunks': num_chunks,
            'total_tokens': total_tokens,
            'avg_per_chunk': total_tokens / num_chunks if num_chunks > 0 else 0
        }


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Test chunk-size optimization on synthetic conversations (Bonsai 9B)"
    )
    parser.add_argument(
        "--turns",
        type=int,
        default=48,
        help="Number of turns in synthetic conversation (default: 48, matching AMD)"
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=101,
        help="Random seed for synthetic generation (default: 101, matching AMD)"
    )
    parser.add_argument(
        "--chunk-sizes",
        type=str,
        default="1,2,4,8",
        help="Comma-separated chunk sizes to test (default: 1,2,4,8)"
    )

    args = parser.parse_args()
    chunk_sizes = [int(x) for x in args.chunk_sizes.split(',')]

    print("=" * 70)
    print("CHUNK-SIZE OPTIMIZATION TEST (Bonsai 9B)")
    print("=" * 70)
    print()
    print(f"Model: Ternary-Bonsai-2-9B-PQ2_0 (port 8080)")
    print(f"Synthetic turns: {args.turns}")
    print(f"Seed: {args.seed}")
    print(f"Chunk sizes: {chunk_sizes}")
    print()

    # Check Bonsai is available
    try:
        response = requests.get("http://localhost:8080/health", timeout=5)
        if response.status_code != 200:
            print("ERROR: Bonsai model not available on port 8080")
            sys.exit(1)
    except Exception as e:
        print(f"ERROR: Cannot connect to Bonsai on port 8080: {e}")
        sys.exit(1)

    # Generate synthetic conversation
    print("Generating synthetic conversation...")
    turns, planted = generate_nanobot_conversation(args.turns, args.seed)
    print(f"Generated {len(turns)} turns with {len(planted)} planted facts")
    print()
    print("Sample planted facts:")
    for fact in planted[:3]:
        print(f"  - {fact}")
    print()

    # Test each chunk size
    extractor = ChunkSizeExtractor()
    results = []

    for chunk_size in chunk_sizes:
        print(f"Testing chunk_size={chunk_size}...")

        try:
            if chunk_size == 1:
                extracted, metrics = extractor.extract_per_turn(turns)
            else:
                extracted, metrics = extractor.extract_chunked(turns, chunk_size)

            # Score recall
            recalled, missed = score_recall(extracted, planted)

            result = {
                'chunk_size': chunk_size,
                'metrics': metrics,
                'recall': len(recalled),
                'total_facts': len(planted),
                'recall_rate': len(recalled) / len(planted) if planted else 0,
                'recalled': [f.text for f in recalled],
                'missed': [f.text for f in missed]
            }

            results.append(result)

            print(f"  Chunks: {metrics['num_chunks']}")
            print(f"  Total tokens: {metrics['total_tokens']}")
            print(f"  Recall: {len(recalled)}/{len(planted)} ({result['recall_rate']:.1%})")
            if missed:
                print(f"  Missed facts:")
                for fact in missed[:3]:  # Show first 3
                    print(f"    - {fact.text}")
            print()

        except Exception as e:
            print(f"  ERROR: {e}")
            print()

    # Summary
    if not results:
        print("ERROR: No results collected")
        sys.exit(1)

    print("=" * 70)
    print("RESULTS SUMMARY")
    print("=" * 70)
    print()
    print(f"{'Chunk Size':<12} {'Chunks':<8} {'Tokens':<10} {'Recall':<10} {'Savings':<10}")
    print("-" * 70)

    baseline = results[0]
    for r in results:
        savings = 100 * (baseline['metrics']['total_tokens'] - r['metrics']['total_tokens']) / baseline['metrics']['total_tokens']
        print(f"{r['chunk_size']:<12} {r['metrics']['num_chunks']:<8} {r['metrics']['total_tokens']:<10} "
              f"{r['recall']}/{r['total_facts']:<8} {savings:>7.1f}%")

    print()
    print("=" * 70)
    print("ANALYSIS")
    print("=" * 70)
    print()

    # Find best chunk size (balance of savings and recall)
    best = None
    acceptable_recall = 0.75  # 75% recall threshold (AMD's standard)

    for r in results:
        if r['recall_rate'] >= acceptable_recall:
            if best is None or r['metrics']['total_tokens'] < best['metrics']['total_tokens']:
                best = r

    if best:
        savings = 100 * (baseline['metrics']['total_tokens'] - best['metrics']['total_tokens']) / baseline['metrics']['total_tokens']
        print(f"✓ Best configuration: chunk_size={best['chunk_size']}")
        print(f"  Token savings: {savings:.1f}% (baseline: {baseline['metrics']['total_tokens']} → {best['metrics']['total_tokens']})")
        print(f"  Recall: {best['recall']}/{best['total_facts']} ({best['recall_rate']:.1%})")
        print(f"  Number of chunks: {best['metrics']['num_chunks']}")
        print()
        print("  AMD comparison:")
        print(f"    AMD (9B, chunk32): 59% savings, 8/8 recall (100%)")
        print(f"    Ours (9B, chunk{best['chunk_size']}): {savings:.1f}% savings, {best['recall_rate']:.0%} recall")
    else:
        print("✗ No configuration met recall threshold (≥75%)")
        print()
        print("  Best recall achieved:")
        best_recall = max(results, key=lambda r: r['recall_rate'])
        print(f"    chunk_size={best_recall['chunk_size']}: {best_recall['recall']}/{best_recall['total_facts']} ({best_recall['recall_rate']:.1%})")

    print()

    # Save results
    output_file = Path(__file__).parent.parent / "results" / f"chunk_size_seed{args.seed}.json"
    output_file.parent.mkdir(exist_ok=True)

    with open(output_file, 'w') as f:
        json.dump({
            'seed': args.seed,
            'num_turns': args.turns,
            'planted_facts': len(planted),
            'results': results,
            'best': best,
        }, f, indent=2)

    print(f"Results saved to: {output_file}")


if __name__ == "__main__":
    main()
