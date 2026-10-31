#!/usr/bin/env python3
"""
Nanobot Patches for ANE Integration

This script patches nanobot for:
1. ANE context provider - injects compressed conversation history
2. Log level environment variable - respects LOGURU_LEVEL env var

Usage:
    python nanobot_ane_patch.py [--apply | --revert | --status]

Patches:
    <site-packages>/nanobot/cli/gateway_runtime.py  - ANE context provider
    <site-packages>/nanobot/utils/log_config.py     - LOGURU_LEVEL support
"""

import argparse
import shutil
import sys
from pathlib import Path

# ============================================================================
# Patch 1: ANE Context Provider (gateway_runtime.py)
# ============================================================================

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

ANE_PATCH_MARKER = "# ANE Context Provider - injected by nanobot_ane_patch.py"

# ============================================================================
# Patch 2: Log Level Environment Variable (log_config.py)
# ============================================================================

LOG_LEVEL_PATCH_MARKER = "# LOGURU_LEVEL env var - injected by nanobot_ane_patch.py"

LOG_LEVEL_ORIGINAL = '''def configure_console_logging(stream: Any, *, level: str = "INFO") -> int:
    """Replace existing handlers with the standard nanobot console sink."""
    logger.remove()
    return add_console_log_sink(stream, level=level)'''

LOG_LEVEL_PATCHED = '''def configure_console_logging(stream: Any, *, level: str | None = None) -> int:
    # LOGURU_LEVEL env var - injected by nanobot_ane_patch.py
    """Replace existing handlers with the standard nanobot console sink."""
    import os
    if level is None:
        level = os.environ.get("LOGURU_LEVEL", "INFO")
    logger.remove()
    return add_console_log_sink(stream, level=level)'''

# ============================================================================
# Helper Functions
# ============================================================================

def find_nanobot_path() -> Path:
    """Find the nanobot package in site-packages."""
    import nanobot
    return Path(nanobot.__file__).parent


def get_gateway_runtime_path() -> Path:
    """Get path to gateway_runtime.py."""
    return find_nanobot_path() / "cli" / "gateway_runtime.py"


def get_log_config_path() -> Path:
    """Get path to log_config.py."""
    return find_nanobot_path() / "utils" / "log_config.py"


def is_ane_patched(content: str) -> bool:
    """Check if the ANE context provider patch is applied."""
    return ANE_PATCH_MARKER in content


def is_log_level_patched(content: str) -> bool:
    """Check if the log level patch is applied."""
    return LOG_LEVEL_PATCH_MARKER in content


def create_backup(path: Path) -> Path:
    """Create a backup of the file if it doesn't exist."""
    backup_path = path.with_suffix('.py.bak')
    if not backup_path.exists():
        shutil.copy(path, backup_path)
        print(f"  Backup created: {backup_path}")
    return backup_path


def clear_pycache(nanobot_path: Path) -> None:
    """Clear Python cache to ensure patches take effect."""
    import shutil
    for cache_dir in nanobot_path.rglob("__pycache__"):
        shutil.rmtree(cache_dir, ignore_errors=True)
    print("  Cleared __pycache__ directories")

# ============================================================================
# ANE Context Provider Patch
# ============================================================================

def apply_ane_patch(path: Path, dry_run: bool = False) -> bool:
    """Apply the ANE context provider patch."""
    content = path.read_text()

    if is_ane_patched(content):
        print(f"  Already patched: {path.name}")
        return True

    if not dry_run:
        create_backup(path)

    # Find insertion points
    lines = content.split('\n')
    new_lines = []

    import_inserted = False
    function_inserted = False
    registration_inserted = False

    for i, line in enumerate(lines):
        new_lines.append(line)

        # Insert imports after the existing imports
        if not import_inserted and "from nanobot.webui.dev import" in line:
            new_lines.append(ANE_PROVIDER_IMPORTS)
            import_inserted = True

        # Insert function before the _run_gateway function definition
        if not function_inserted and line.strip().startswith("def _run_gateway("):
            new_lines.pop()
            new_lines.append(ANE_PROVIDER_FUNCTION)
            new_lines.append(line)
            function_inserted = True

        # Insert registration before def _schedule_webui_background
        if not registration_inserted and "def _schedule_webui_background" in line:
            new_lines.pop()
            new_lines.append(ANE_PROVIDER_REGISTRATION)
            new_lines.append(line)
            registration_inserted = True

    if not (import_inserted and function_inserted and registration_inserted):
        print(f"  ERROR: Could not find all insertion points in {path.name}")
        return False

    if dry_run:
        print(f"  Would patch: {path.name}")
        return True

    path.write_text('\n'.join(new_lines))
    print(f"  Patched: {path.name}")
    return True


def revert_ane_patch(path: Path) -> bool:
    """Revert the ANE patch using backup."""
    backup_path = path.with_suffix('.py.bak')

    if not backup_path.exists():
        print(f"  No backup found for {path.name}")
        return False

    shutil.copy(backup_path, path)
    backup_path.unlink()
    print(f"  Reverted: {path.name}")
    return True

# ============================================================================
# Log Level Patch
# ============================================================================

def apply_log_level_patch(path: Path, dry_run: bool = False) -> bool:
    """Apply the LOGURU_LEVEL environment variable patch."""
    content = path.read_text()

    if is_log_level_patched(content):
        print(f"  Already patched: {path.name}")
        return True

    if LOG_LEVEL_ORIGINAL not in content:
        print(f"  ERROR: Could not find target code in {path.name}")
        return False

    if not dry_run:
        create_backup(path)

    new_content = content.replace(LOG_LEVEL_ORIGINAL, LOG_LEVEL_PATCHED)

    if dry_run:
        print(f"  Would patch: {path.name}")
        return True

    path.write_text(new_content)
    print(f"  Patched: {path.name}")
    return True


def revert_log_level_patch(path: Path) -> bool:
    """Revert the log level patch using backup."""
    backup_path = path.with_suffix('.py.bak')

    if not backup_path.exists():
        print(f"  No backup found for {path.name}")
        return False

    shutil.copy(backup_path, path)
    backup_path.unlink()
    print(f"  Reverted: {path.name}")
    return True

# ============================================================================
# Main
# ============================================================================

def check_status() -> None:
    """Check patch status for all files."""
    try:
        nanobot_path = find_nanobot_path()
    except ImportError:
        print("ERROR: nanobot package not found")
        return

    print(f"Nanobot location: {nanobot_path}")
    print()

    # ANE patch
    gateway_path = get_gateway_runtime_path()
    if gateway_path.exists():
        content = gateway_path.read_text()
        ane_patched = is_ane_patched(content)
        ane_backup = gateway_path.with_suffix('.py.bak').exists()
        print(f"ANE Context Provider ({gateway_path.name}):")
        print(f"  Patched: {ane_patched}")
        print(f"  Backup exists: {ane_backup}")
    else:
        print(f"ANE Context Provider: File not found")

    print()

    # Log level patch
    log_config_path = get_log_config_path()
    if log_config_path.exists():
        content = log_config_path.read_text()
        log_patched = is_log_level_patched(content)
        log_backup = log_config_path.with_suffix('.py.bak').exists()
        print(f"Log Level Env Var ({log_config_path.name}):")
        print(f"  Patched: {log_patched}")
        print(f"  Backup exists: {log_backup}")
    else:
        print(f"Log Level Env Var: File not found")


def apply_all(dry_run: bool = False) -> bool:
    """Apply all patches."""
    try:
        nanobot_path = find_nanobot_path()
    except ImportError:
        print("ERROR: nanobot package not found")
        return False

    print(f"Nanobot location: {nanobot_path}")
    print()

    success = True

    # ANE patch
    print("1. ANE Context Provider:")
    gateway_path = get_gateway_runtime_path()
    if not apply_ane_patch(gateway_path, dry_run):
        success = False

    print()

    # Log level patch
    print("2. Log Level Env Var (LOGURU_LEVEL):")
    log_config_path = get_log_config_path()
    if not apply_log_level_patch(log_config_path, dry_run):
        success = False

    if not dry_run and success:
        print()
        clear_pycache(nanobot_path)

    return success


def revert_all() -> bool:
    """Revert all patches."""
    try:
        nanobot_path = find_nanobot_path()
    except ImportError:
        print("ERROR: nanobot package not found")
        return False

    print(f"Nanobot location: {nanobot_path}")
    print()

    success = True

    # ANE patch
    print("1. ANE Context Provider:")
    gateway_path = get_gateway_runtime_path()
    if not revert_ane_patch(gateway_path):
        success = False

    print()

    # Log level patch
    print("2. Log Level Env Var:")
    log_config_path = get_log_config_path()
    if not revert_log_level_patch(log_config_path):
        success = False

    if success:
        print()
        clear_pycache(nanobot_path)

    return success


def main():
    parser = argparse.ArgumentParser(
        description="Patch nanobot for ANE integration and log level support"
    )
    parser.add_argument(
        "--apply", action="store_true",
        help="Apply all patches"
    )
    parser.add_argument(
        "--revert", action="store_true",
        help="Revert all patches"
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

    if args.status or not (args.apply or args.revert):
        check_status()
        return

    if args.apply:
        if apply_all(dry_run=args.dry_run):
            if not args.dry_run:
                print()
                print("✓ All patches applied successfully!")
                print()
                print("Restart nanobot gateway for changes to take effect:")
                print("  launchctl unload ~/Library/LaunchAgents/com.nanobot.gateway.plist")
                print("  launchctl load ~/Library/LaunchAgents/com.nanobot.gateway.plist")
        else:
            print()
            print("✗ Some patches failed")
            sys.exit(1)

    elif args.revert:
        if revert_all():
            print()
            print("✓ All patches reverted successfully!")
            print()
            print("Restart nanobot gateway for changes to take effect:")
            print("  launchctl unload ~/Library/LaunchAgents/com.nanobot.gateway.plist")
            print("  launchctl load ~/Library/LaunchAgents/com.nanobot.gateway.plist")
        else:
            print()
            print("✗ Some reverts failed")
            sys.exit(1)


if __name__ == "__main__":
    main()
