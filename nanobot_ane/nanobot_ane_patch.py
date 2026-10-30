#!/usr/bin/env python3
"""
Nanobot ANE Context Provider Patch

This script patches nanobot to automatically register the ANE context provider
that injects compressed conversation history before each inference.

Usage:
    python nanobot_ane_patch.py [--apply | --revert | --status]

The patch modifies:
    <site-packages>/nanobot/cli/gateway_runtime.py

To add the ANE context provider that fetches compressed history from
http://127.0.0.1:8766/context/{session_key}
"""

import argparse
import shutil
import sys
from pathlib import Path

# The code to inject
ANE_PROVIDER_IMPORTS = '''
# ANE Context Provider - injected by nanobot_ane_patch.py
import aiohttp
from nanobot.runtime_context import RuntimeContextBlock
'''

ANE_PROVIDER_FUNCTION = '''
# ANE Context Provider - injected by nanobot_ane_patch.py
async def _ane_context_provider(request_context):
    """Fetch compressed context from ANE daemon."""
    from loguru import logger as _ane_logger
    session_key = getattr(request_context, 'session_key', None)
    if not session_key:
        return None

    # Extract chat_id from session_key (format: "channel:chat_id")
    chat_id = session_key.split(":", 1)[-1] if ":" in session_key else session_key

    try:
        async with aiohttp.ClientSession() as session:
            # Use chat_id (how ANE daemon stores sessions)
            url = f"http://127.0.0.1:8766/context/{chat_id}"
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=2.0)) as response:
                if response.status != 200:
                    return None
                data = await response.json()
                context = data.get("context", "")
                if not context:
                    return None
                _ane_logger.info("ANE: injected {} chars for {}", len(context), chat_id[:16])
                return RuntimeContextBlock(source="ane_compression", content=context)
    except Exception as e:
        _ane_logger.debug("ANE provider error: {}", e)
        return None
'''

ANE_PROVIDER_REGISTRATION = '''
    # Register ANE context provider - injected by nanobot_ane_patch.py
    agent.register_runtime_context_provider(_ane_context_provider)
    logger.info("ANE context provider registered (http://127.0.0.1:8766)")
'''

# Markers to identify patched code
PATCH_MARKER = "# ANE Context Provider - injected by nanobot_ane_patch.py"


def find_nanobot_path() -> Path:
    """Find the nanobot package in site-packages."""
    import nanobot
    return Path(nanobot.__file__).parent


def get_gateway_runtime_path() -> Path:
    """Get path to gateway_runtime.py."""
    return find_nanobot_path() / "cli" / "gateway_runtime.py"


def is_patched(content: str) -> bool:
    """Check if the file is already patched."""
    return PATCH_MARKER in content


def apply_patch(path: Path, dry_run: bool = False) -> bool:
    """Apply the ANE context provider patch."""
    content = path.read_text()

    if is_patched(content):
        print(f"Already patched: {path}")
        return True

    # Create backup
    backup_path = path.with_suffix('.py.bak')
    if not dry_run:
        shutil.copy(path, backup_path)
        print(f"Backup created: {backup_path}")

    # Find insertion points
    lines = content.split('\n')
    new_lines = []

    import_inserted = False
    function_inserted = False
    registration_inserted = False

    for i, line in enumerate(lines):
        new_lines.append(line)

        # Insert imports after the existing imports (after "from nanobot.webui.dev import")
        if not import_inserted and "from nanobot.webui.dev import" in line:
            new_lines.append(ANE_PROVIDER_IMPORTS)
            import_inserted = True

        # Insert function before the _run_gateway function definition
        if not function_inserted and line.strip().startswith("def _run_gateway("):
            # Insert the function before this line
            new_lines.pop()  # Remove the line we just added
            new_lines.append(ANE_PROVIDER_FUNCTION)
            new_lines.append(line)  # Re-add the line
            function_inserted = True

        # Insert registration after the def _schedule_webui_background line
        # This is right after the AgentLoop.from_config() call
        if not registration_inserted and "def _schedule_webui_background" in line:
            # Insert registration before this line
            new_lines.pop()  # Remove the line we just added
            new_lines.append(ANE_PROVIDER_REGISTRATION)
            new_lines.append(line)  # Re-add the line
            registration_inserted = True

    if not (import_inserted and function_inserted and registration_inserted):
        print("ERROR: Could not find all insertion points. Manual patching may be required.")
        print(f"  Imports inserted: {import_inserted}")
        print(f"  Function inserted: {function_inserted}")
        print(f"  Registration inserted: {registration_inserted}")
        return False

    new_content = '\n'.join(new_lines)

    if dry_run:
        print(f"Would patch: {path}")
        print(f"  - Add imports after 'from nanobot.webui.dev import'")
        print(f"  - Add _ane_context_provider function")
        print(f"  - Register provider after AgentLoop.from_config()")
        return True

    path.write_text(new_content)
    print(f"Patched: {path}")
    return True


def revert_patch(path: Path) -> bool:
    """Revert the patch using backup."""
    backup_path = path.with_suffix('.py.bak')

    if not backup_path.exists():
        print(f"No backup found: {backup_path}")
        return False

    shutil.copy(backup_path, path)
    backup_path.unlink()
    print(f"Reverted: {path}")
    print(f"Removed backup: {backup_path}")
    return True


def check_status(path: Path) -> None:
    """Check patch status."""
    content = path.read_text()
    backup_path = path.with_suffix('.py.bak')

    print(f"File: {path}")
    print(f"Patched: {is_patched(content)}")
    print(f"Backup exists: {backup_path.exists()}")


def main():
    parser = argparse.ArgumentParser(
        description="Patch nanobot to include ANE context provider"
    )
    parser.add_argument(
        "--apply", action="store_true",
        help="Apply the patch"
    )
    parser.add_argument(
        "--revert", action="store_true",
        help="Revert the patch"
    )
    parser.add_argument(
        "--status", action="store_true",
        help="Check patch status"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Show what would be done without making changes"
    )

    args = parser.parse_args()

    try:
        path = get_gateway_runtime_path()
    except ImportError:
        print("ERROR: nanobot package not found. Is it installed?")
        sys.exit(1)

    if args.status or not (args.apply or args.revert):
        check_status(path)
        return

    if args.apply:
        if apply_patch(path, dry_run=args.dry_run):
            if not args.dry_run:
                print("\n✓ Patch applied successfully!")
                print("  Restart nanobot gateway for changes to take effect:")
                print("    nanobot gateway restart")
        else:
            sys.exit(1)

    elif args.revert:
        if revert_patch(path):
            print("\n✓ Patch reverted successfully!")
            print("  Restart nanobot gateway for changes to take effect:")
            print("    nanobot gateway restart")
        else:
            sys.exit(1)


if __name__ == "__main__":
    main()
