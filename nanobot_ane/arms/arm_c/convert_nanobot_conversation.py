#!/usr/bin/env python3
"""
Convert nanobot conversation JSONL files to format for quality checker.

Reads nanobot .jsonl conversation files and extracts user/assistant message pairs.
"""
import json
import sys
from pathlib import Path
from typing import List, Dict


def load_nanobot_conversation(jsonl_path: str) -> List[Dict]:
    """
    Load nanobot conversation from JSONL file.

    Returns list of messages with role and content.
    """
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

                # Only include user and assistant messages
                if role in ('user', 'assistant'):
                    messages.append({
                        'role': role,
                        'content': content
                    })
            except json.JSONDecodeError:
                continue

    return messages


def filter_conversation_pairs(messages: List[Dict]) -> List[Dict]:
    """
    Filter to only include user/assistant pairs.

    Ensures we have clean turn pairs for testing.
    """
    filtered = []

    i = 0
    while i < len(messages) - 1:
        if messages[i]['role'] == 'user' and messages[i+1]['role'] == 'assistant':
            filtered.append(messages[i])
            filtered.append(messages[i+1])
            i += 2
        else:
            i += 1

    return filtered


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Convert nanobot conversation to quality-check format"
    )
    parser.add_argument(
        "input",
        type=str,
        help="Path to nanobot .jsonl conversation file"
    )
    parser.add_argument(
        "--output",
        type=str,
        help="Output JSON file (default: stdout)"
    )
    parser.add_argument(
        "--stats",
        action="store_true",
        help="Print statistics about the conversation"
    )

    args = parser.parse_args()

    # Load conversation
    input_path = Path(args.input).expanduser()
    if not input_path.exists():
        print(f"Error: File not found: {input_path}", file=sys.stderr)
        sys.exit(1)

    messages = load_nanobot_conversation(str(input_path))
    filtered = filter_conversation_pairs(messages)

    if args.stats:
        print(f"Conversation: {input_path.name}", file=sys.stderr)
        print(f"Total messages: {len(messages)}", file=sys.stderr)
        print(f"User/assistant pairs: {len(filtered) // 2}", file=sys.stderr)
        print(f"Filtered messages: {len(filtered)}", file=sys.stderr)
        print(file=sys.stderr)

    # Output
    if args.output:
        output_path = Path(args.output)
        with open(output_path, 'w') as f:
            json.dump(filtered, f, indent=2)
        print(f"Saved to: {output_path}", file=sys.stderr)
    else:
        print(json.dumps(filtered, indent=2))


if __name__ == "__main__":
    main()
