#!/usr/bin/env python3
"""
Fallback patcher for memory.py when standard patch fails.
Handles nanobot version differences by finding insertion points.
"""

import sys
import re
from pathlib import Path

ANE_IMPORT_BLOCK = '''
# ANE compression integration
try:
    from nanobot.agent.ane_client import get_ane_client, ANEClient
    _ANE_AVAILABLE = True
except ImportError:
    _ANE_AVAILABLE = False
    ANEClient = None  # type: ignore

    def get_ane_client():  # type: ignore
        return None
'''

ANE_ARCHIVE_BLOCK = '''
        # ── TRY ANE COMPRESSION FIRST ──
        # ANE runs on Apple Neural Engine - much faster and doesn't use API credits
        if _ANE_AVAILABLE:
            ane_client = get_ane_client()
            if ane_client is not None:
                try:
                    if await ane_client.is_available():
                        ane_summary = await ane_client.compress_session(
                            session_key,
                            source_messages,
                            previous_summary,
                        )
                        if ane_summary:
                            logger.info(
                                "ANE compression succeeded for {}: {} chars",
                                session_key[:16],
                                len(ane_summary),
                            )
                            # Persist to history journal if requested
                            if persist and ane_summary != "(nothing)":
                                self.store.append_history(
                                    ane_summary,
                                    session_key=session_key,
                                )
                            return ane_summary
                        else:
                            logger.debug(
                                "ANE compression returned no result for {}; "
                                "falling back to native",
                                session_key[:16],
                            )
                except Exception as e:
                    logger.debug(
                        "ANE compression failed for {}: {}; falling back to native",
                        session_key[:16],
                        e,
                    )

        # ── NATIVE LLM SUMMARIZATION (fallback) ──
'''


def patch_memory_py(filepath: str) -> bool:
    """Apply ANE integration patches to memory.py"""
    path = Path(filepath)
    content = path.read_text()

    # Check if already patched
    if "ANE compression integration" in content:
        print("Already patched, skipping")
        return True

    modified = False

    # 1. Add import block after TYPE_CHECKING imports
    import_pattern = r'(if TYPE_CHECKING:.*?from nanobot\.agent\.tools\.registry import ToolRegistry\n)'
    import_match = re.search(import_pattern, content, re.DOTALL)

    if import_match:
        insert_pos = import_match.end()
        content = content[:insert_pos] + ANE_IMPORT_BLOCK + content[insert_pos:]
        modified = True
        print("Added ANE import block")
    else:
        print("Warning: Could not find TYPE_CHECKING block for import insertion")

    # 2. Add archive integration after "if not source_messages: return None"
    archive_pattern = r'(async def archive\(.*?if not source_messages:\s*\n\s*return None\n)'
    archive_match = re.search(archive_pattern, content, re.DOTALL)

    if archive_match:
        insert_pos = archive_match.end()
        content = content[:insert_pos] + ANE_ARCHIVE_BLOCK + content[insert_pos:]
        modified = True
        print("Added ANE archive integration block")
    else:
        print("Warning: Could not find archive() method for integration insertion")

    if modified:
        path.write_text(content)
        print(f"Patched: {filepath}")
        return True
    else:
        print("No modifications made")
        return False


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <path/to/memory.py>")
        sys.exit(1)

    success = patch_memory_py(sys.argv[1])
    sys.exit(0 if success else 1)
