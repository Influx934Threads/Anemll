#!/usr/bin/env python3
"""
Test Budget 100 on real nanobot conversations.

Compares baseline vs Budget 100 on actual conversation data to see
real-world output quality difference.
"""
import sys
import asyncio
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from ane_inference import ANEInference
from arms.shared import TokenCounter


class FactExtractor:
    """Extract facts with configurable prompts"""

    def __init__(self, model_path: str):
        self.inference = ANEInference(model_path)
        self.token_counter = TokenCounter()

    def extract_baseline(self, turn_text: str) -> tuple[str, dict]:
        """Baseline prompt (current production)"""
        prompt = f"""Extract facts from this conversation turn. Be concise and specific.

Turn:
{turn_text}

Facts:"""

        output = asyncio.run(self.inference.generate(
            prompt=prompt,
            max_tokens=200,
            temperature=0.0
        ))

        metrics = {
            'variant': 'baseline',
            'output_tokens': self.token_counter.count(output)
        }

        return output, metrics

    def extract_budget100(self, turn_text: str) -> tuple[str, dict]:
        """Budget 100 with moderate concision + preserve details"""
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

        metrics = {
            'variant': 'budget100',
            'output_tokens': self.token_counter.count(output)
        }

        return output, metrics


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
        description="Test Budget 100 on real nanobot conversations"
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
    print("BUDGET 100 vs BASELINE - REAL CONVERSATION TEST")
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

    # Initialize extractor
    extractor = FactExtractor(args.model)

    # Process each turn
    results = []

    for i, turn in enumerate(turns):
        print(f"Turn {i+1}/{len(turns)}")
        print("-" * 70)
        print(f"User: {turn['user'][:100]}...")
        print(f"Assistant: {turn['assistant'][:100]}...")
        print()

        # Extract with baseline
        print("Baseline extraction...")
        baseline_output, baseline_metrics = extractor.extract_baseline(turn['turn_text'])

        # Extract with budget100
        print("Budget 100 extraction...")
        budget100_output, budget100_metrics = extractor.extract_budget100(turn['turn_text'])

        results.append({
            'turn_num': i + 1,
            'user': turn['user'],
            'assistant': turn['assistant'],
            'baseline': {
                'output': baseline_output,
                'tokens': baseline_metrics['output_tokens']
            },
            'budget100': {
                'output': budget100_output,
                'tokens': budget100_metrics['output_tokens']
            }
        })

        print(f"✓ Baseline: {baseline_metrics['output_tokens']} tokens")
        print(f"✓ Budget100: {budget100_metrics['output_tokens']} tokens "
              f"({100 * (baseline_metrics['output_tokens'] - budget100_metrics['output_tokens']) / baseline_metrics['output_tokens']:.1f}% savings)")
        print()

    # Summary
    print("=" * 70)
    print("SIDE-BY-SIDE COMPARISON")
    print("=" * 70)
    print()

    total_baseline_tokens = 0
    total_budget100_tokens = 0

    for r in results:
        print(f"TURN {r['turn_num']}")
        print("=" * 70)
        print()
        print(f"User: {r['user'][:200]}")
        if len(r['user']) > 200:
            print(f"... ({len(r['user']) - 200} more chars)")
        print()
        print(f"Assistant: {r['assistant'][:200]}")
        if len(r['assistant']) > 200:
            print(f"... ({len(r['assistant']) - 200} more chars)")
        print()

        print("BASELINE OUTPUT:")
        print(f"  Tokens: {r['baseline']['tokens']}")
        print("-" * 70)
        print(r['baseline']['output'])
        print("-" * 70)
        print()

        print("BUDGET 100 OUTPUT:")
        print(f"  Tokens: {r['budget100']['tokens']}")
        print("-" * 70)
        print(r['budget100']['output'])
        print("-" * 70)
        print()

        print("QUALITY COMPARISON:")
        baseline_len = len(r['baseline']['output'])
        budget_len = len(r['budget100']['output'])
        print(f"  Length: {baseline_len} vs {budget_len} chars ({100 * (baseline_len - budget_len) / baseline_len:.1f}% shorter)")
        print(f"  Tokens: {r['baseline']['tokens']} vs {r['budget100']['tokens']} ({100 * (r['baseline']['tokens'] - r['budget100']['tokens']) / r['baseline']['tokens']:.1f}% savings)")
        print()
        print()

        total_baseline_tokens += r['baseline']['tokens']
        total_budget100_tokens += r['budget100']['tokens']

    # Overall stats
    print("=" * 70)
    print("OVERALL STATISTICS")
    print("=" * 70)
    print()
    print(f"Turns tested: {len(results)}")
    print()
    print(f"Baseline:")
    print(f"  Total tokens: {total_baseline_tokens}")
    print(f"  Avg per turn: {total_baseline_tokens / len(results):.1f}")
    print()
    print(f"Budget 100:")
    print(f"  Total tokens: {total_budget100_tokens}")
    print(f"  Avg per turn: {total_budget100_tokens / len(results):.1f}")
    print()
    print(f"Token savings: {total_baseline_tokens - total_budget100_tokens} tokens ({100 * (total_baseline_tokens - total_budget100_tokens) / total_baseline_tokens:.1f}%)")
    print()

    # Qualitative assessment
    print("=" * 70)
    print("QUALITATIVE ASSESSMENT")
    print("=" * 70)
    print()
    print("Review the side-by-side outputs above to assess:")
    print("  1. Does Budget 100 preserve key information?")
    print("  2. Are numbers, paths, and specifics maintained?")
    print("  3. Is the compression acceptable for production?")
    print("  4. Any critical information loss?")
    print()


if __name__ == "__main__":
    main()
