#!/usr/bin/env python3
"""
Test Budget 100 Enhanced with explicit content-scanning cues.

Based on AMD NPU finding: explicit cues for "orphaned" critical facts
rescued recall from 6/8 to 8/8. Testing if this reduces Budget 100's
14% quality drop.
"""
import sys
import asyncio
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from ane_inference import ANEInference
from arms.shared import TokenCounter


class Budget100Variants:
    """Test Budget 100 original vs enhanced with explicit cues"""

    def __init__(self, model_path: str):
        self.inference = ANEInference(model_path)
        self.token_counter = TokenCounter()

    def extract_budget100_original(self, turn_text: str) -> tuple[str, dict]:
        """Budget 100 original (current)"""
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
            'variant': 'budget100_original',
            'output_tokens': self.token_counter.count(output)
        }

        return output, metrics

    def extract_budget100_enhanced(self, turn_text: str) -> tuple[str, dict]:
        """Budget 100 enhanced with AMD NPU-inspired explicit content cues (no examples)"""
        prompt = f"""Extract facts from this conversation turn. Target ≤100 tokens.
Be concise but clear. Abbreviate where unambiguous.

CRITICAL: Scan explicitly for these types even if buried in unrelated content:
- File paths: any absolute paths, relative paths, or home directory shortcuts
- Model identifiers: names, versions, size specifications
- Configuration settings: key=value pairs, numeric parameters, timeouts
- Error details: error messages, status codes, errno values
- User decisions: choices made, preferences set, features enabled or disabled
- Standalone notes: observations marked as "Note:", "Important:", "Remember:", or similar

Do not let surrounding code, logs, or unrelated content crowd out these facts.
Extract ONLY what appears in the turn - do not invent examples.

Turn:
{turn_text}

Facts (≤100 tokens):"""

        output = asyncio.run(self.inference.generate(
            prompt=prompt,
            max_tokens=120,  # Small buffer
            temperature=0.0
        ))

        metrics = {
            'variant': 'budget100_enhanced',
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
        description="Test Budget 100 Enhanced with explicit content cues"
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
    print("BUDGET 100 ENHANCED vs ORIGINAL - CONTENT CUE TEST")
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
    extractor = Budget100Variants(args.model)

    # Process each turn
    results = []

    for i, turn in enumerate(turns):
        print(f"Turn {i+1}/{len(turns)}")
        print("-" * 70)
        print(f"User: {turn['user'][:100]}...")
        print(f"Assistant: {turn['assistant'][:100]}...")
        print()

        # Extract with original
        print("Budget 100 Original...")
        original_output, original_metrics = extractor.extract_budget100_original(turn['turn_text'])

        # Extract with enhanced
        print("Budget 100 Enhanced...")
        enhanced_output, enhanced_metrics = extractor.extract_budget100_enhanced(turn['turn_text'])

        results.append({
            'turn_num': i + 1,
            'user': turn['user'],
            'assistant': turn['assistant'],
            'original': {
                'output': original_output,
                'tokens': original_metrics['output_tokens']
            },
            'enhanced': {
                'output': enhanced_output,
                'tokens': enhanced_metrics['output_tokens']
            }
        })

        print(f"✓ Original: {original_metrics['output_tokens']} tokens")
        print(f"✓ Enhanced: {enhanced_metrics['output_tokens']} tokens")
        print()

    # Summary
    print("=" * 70)
    print("SIDE-BY-SIDE COMPARISON")
    print("=" * 70)
    print()

    total_original_tokens = 0
    total_enhanced_tokens = 0

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

        print("ORIGINAL OUTPUT:")
        print(f"  Tokens: {r['original']['tokens']}")
        print("-" * 70)
        print(r['original']['output'])
        print("-" * 70)
        print()

        print("ENHANCED OUTPUT:")
        print(f"  Tokens: {r['enhanced']['tokens']}")
        print("-" * 70)
        print(r['enhanced']['output'])
        print("-" * 70)
        print()

        print("QUALITY COMPARISON:")
        original_len = len(r['original']['output'])
        enhanced_len = len(r['enhanced']['output'])

        # Check for additional detail preservation
        original_has_paths = '/' in r['original']['output'] or '~' in r['original']['output']
        enhanced_has_paths = '/' in r['enhanced']['output'] or '~' in r['enhanced']['output']

        original_has_versions = any(c.isdigit() and '.' in r['original']['output'][max(0,i-5):i+5]
                                    for i, c in enumerate(r['original']['output']) if c.isdigit())
        enhanced_has_versions = any(c.isdigit() and '.' in r['enhanced']['output'][max(0,i-5):i+5]
                                    for i, c in enumerate(r['enhanced']['output']) if c.isdigit())

        print(f"  Length: {original_len} vs {enhanced_len} chars")
        print(f"  Tokens: {r['original']['tokens']} vs {r['enhanced']['tokens']}")
        print(f"  File paths: {'✓' if original_has_paths else '✗'} vs {'✓' if enhanced_has_paths else '✗'}")
        print(f"  Version numbers: {'✓' if original_has_versions else '✗'} vs {'✓' if enhanced_has_versions else '✗'}")
        print()
        print()

        total_original_tokens += r['original']['tokens']
        total_enhanced_tokens += r['enhanced']['tokens']

    # Overall stats
    print("=" * 70)
    print("OVERALL STATISTICS")
    print("=" * 70)
    print()
    print(f"Turns tested: {len(results)}")
    print()
    print(f"Budget 100 Original:")
    print(f"  Total tokens: {total_original_tokens}")
    print(f"  Avg per turn: {total_original_tokens / len(results):.1f}")
    print()
    print(f"Budget 100 Enhanced:")
    print(f"  Total tokens: {total_enhanced_tokens}")
    print(f"  Avg per turn: {total_enhanced_tokens / len(results):.1f}")
    print()

    token_diff = total_enhanced_tokens - total_original_tokens
    if token_diff > 0:
        print(f"Enhanced uses {token_diff} MORE tokens ({100 * token_diff / total_original_tokens:.1f}% increase)")
    elif token_diff < 0:
        print(f"Enhanced uses {-token_diff} FEWER tokens ({100 * -token_diff / total_original_tokens:.1f}% savings)")
    else:
        print(f"Same token count")
    print()

    # Assessment
    print("=" * 70)
    print("QUALITATIVE ASSESSMENT")
    print("=" * 70)
    print()
    print("Review the side-by-side outputs above to assess:")
    print("  1. Does Enhanced preserve more critical details (paths, versions, configs)?")
    print("  2. Does Enhanced better capture 'orphaned' observations?")
    print("  3. Is any quality improvement worth the token cost difference?")
    print("  4. Should we adopt Enhanced as the new Budget 100 standard?")
    print()


if __name__ == "__main__":
    main()
