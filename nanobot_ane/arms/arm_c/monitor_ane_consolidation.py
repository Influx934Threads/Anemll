#!/usr/bin/env python3
"""
Monitor ANE consolidation in real-time during nanobot conversations.

Watches the ANE state file and reports when consolidation happens.
"""
import json
import time
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, Optional


ANE_STATE_FILE = Path.home() / ".nanobot" / "run" / "ane_state.json"


def load_ane_state() -> Optional[Dict]:
    """Load current ANE state"""
    if not ANE_STATE_FILE.exists():
        return None

    try:
        with open(ANE_STATE_FILE, 'r') as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return None


def get_session_info(state: Dict, session_key: str) -> Optional[Dict]:
    """Get info for a specific session"""
    sessions = state.get('sessions', {})
    return sessions.get(session_key)


def print_session_summary(session_key: str, session: Dict):
    """Print summary of a session"""
    print(f"\n{'='*70}")
    print(f"Session: {session_key[:16]}...")
    print(f"{'='*70}")

    turn_count = session.get('turn_count', 0)
    facts = session.get('facts', [])
    text = session.get('text', '')
    token_estimate = session.get('token_estimate', 0)
    last_updated = session.get('last_updated', '')

    print(f"Turn count: {turn_count}")
    print(f"Facts: {len(facts)}")
    print(f"Token estimate: {token_estimate}")
    print(f"Last updated: {last_updated}")
    print()

    if facts:
        print("Recent facts:")
        for i, fact in enumerate(facts[-5:], 1):
            fact_type = fact.get('type', 'unknown')
            content = fact.get('content', '')[:60]
            print(f"  {i}. [{fact_type}] {content}...")
        print()

    if text:
        print("Consolidated text:")
        print("-" * 70)
        print(text[:500])
        if len(text) > 500:
            print(f"... ({len(text) - 500} more chars)")
        print("-" * 70)


def analyze_consolidation(text: str) -> Dict:
    """
    Analyze consolidated text to check if it looks like mechanical merge output.

    Mechanical merge produces structured markdown with sections like:
    - **Configuration:**
    - **Context:**
    - **Result:**
    """
    analysis = {
        'has_markdown_sections': False,
        'has_bullet_lists': False,
        'has_type_headers': False,
        'total_chars': len(text),
        'line_count': len(text.split('\n')),
        'likely_mechanical': False
    }

    # Check for markdown section headers (mechanical merge pattern)
    type_keywords = ['Configuration:', 'Context:', 'Result:', 'Threshold:', 'Schedule:', 'Task:', 'Tool:', 'Location:']
    if any(keyword in text for keyword in type_keywords):
        analysis['has_type_headers'] = True

    # Check for markdown bold headers
    if '**' in text:
        analysis['has_markdown_sections'] = True

    # Check for bullet lists
    if '\n-' in text or '\n* ' in text:
        analysis['has_bullet_lists'] = True

    # Mechanical merge produces structured markdown with type headers and bullets
    if analysis['has_type_headers'] and analysis['has_bullet_lists']:
        analysis['likely_mechanical'] = True

    return analysis


def watch_mode(session_key: Optional[str] = None, interval: int = 2):
    """Watch ANE state for changes"""
    print("=" * 70)
    print("ANE CONSOLIDATION MONITOR")
    print("=" * 70)
    print()
    print(f"Watching: {ANE_STATE_FILE}")
    print(f"Update interval: {interval}s")
    print()

    if session_key:
        print(f"Monitoring session: {session_key}")
    else:
        print("Monitoring all sessions")

    print()
    print("Waiting for consolidation events...")
    print("(Consolidation happens every 5 turns or when >10 facts accumulated)")
    print()

    last_state = {}
    turn = 0

    try:
        while True:
            state = load_ane_state()

            if not state:
                time.sleep(interval)
                continue

            sessions = state.get('sessions', {})

            # Monitor specific session or all sessions
            keys_to_monitor = [session_key] if session_key and session_key in sessions else list(sessions.keys())

            for key in keys_to_monitor:
                session = sessions.get(key)
                if not session:
                    continue

                # Check if this session changed
                last_session = last_state.get(key, {})
                current_turn = session.get('turn_count', 0)
                last_turn = last_session.get('turn_count', 0)

                current_text = session.get('text', '')
                last_text = last_session.get('text', '')

                # Detect consolidation event
                if current_text != last_text:
                    turn += 1
                    timestamp = datetime.now().strftime("%H:%M:%S")

                    print(f"\n[{timestamp}] 🔄 CONSOLIDATION EVENT #{turn}")
                    print(f"Session: {key[:16]}...")
                    print(f"Turn: {last_turn} → {current_turn}")

                    # Analyze the consolidated text
                    if current_text:
                        analysis = analyze_consolidation(current_text)

                        print()
                        print("Consolidation Analysis:")
                        print(f"  Chars: {analysis['total_chars']}")
                        print(f"  Lines: {analysis['line_count']}")
                        print(f"  Markdown sections: {'✓' if analysis['has_markdown_sections'] else '✗'}")
                        print(f"  Type headers: {'✓' if analysis['has_type_headers'] else '✗'}")
                        print(f"  Bullet lists: {'✓' if analysis['has_bullet_lists'] else '✗'}")
                        print()

                        if analysis['likely_mechanical']:
                            print("  ✅ Looks like MECHANICAL MERGE output")
                        else:
                            print("  ⚠️  May be LLM consolidation (lacks mechanical merge structure)")

                        print()
                        print("Consolidated text:")
                        print("-" * 70)
                        print(current_text)
                        print("-" * 70)

                # Update facts count
                current_facts = len(session.get('facts', []))
                last_facts = len(last_session.get('facts', []))

                if current_facts != last_facts:
                    timestamp = datetime.now().strftime("%H:%M:%S")
                    print(f"[{timestamp}] 📝 Facts: {last_facts} → {current_facts} (session {key[:16]}...)")

            last_state = sessions
            time.sleep(interval)

    except KeyboardInterrupt:
        print("\n\nMonitoring stopped.")


def snapshot_mode():
    """Show current state snapshot"""
    print("=" * 70)
    print("ANE STATE SNAPSHOT")
    print("=" * 70)
    print()

    state = load_ane_state()

    if not state:
        print(f"❌ No state file found at: {ANE_STATE_FILE}")
        print()
        print("Is the ANE daemon running?")
        print("Check: ~/.nanobot/logs/ane_daemon.log")
        return

    sessions = state.get('sessions', {})

    print(f"Total sessions: {len(sessions)}")
    print()

    if not sessions:
        print("No active sessions.")
        print()
        print("Start a nanobot conversation to create a session.")
        return

    # Show all sessions
    for i, (key, session) in enumerate(sessions.items(), 1):
        print(f"\n{i}. Session: {key[:16]}...")
        print(f"   Turns: {session.get('turn_count', 0)}")
        print(f"   Facts: {len(session.get('facts', []))}")
        print(f"   Tokens: {session.get('token_estimate', 0)}")

        text = session.get('text', '')
        if text:
            analysis = analyze_consolidation(text)
            status = "✅ Mechanical" if analysis['likely_mechanical'] else "⚠️  Unknown"
            print(f"   Consolidation: {status} ({analysis['total_chars']} chars)")
        else:
            print(f"   Consolidation: None yet")


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Monitor ANE consolidation during nanobot conversations"
    )
    parser.add_argument(
        "--watch",
        action="store_true",
        help="Watch mode: monitor for consolidation events in real-time"
    )
    parser.add_argument(
        "--session",
        type=str,
        help="Monitor specific session key"
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=2,
        help="Update interval in seconds (default: 2)"
    )

    args = parser.parse_args()

    if args.watch:
        watch_mode(session_key=args.session, interval=args.interval)
    else:
        snapshot_mode()


if __name__ == "__main__":
    main()
