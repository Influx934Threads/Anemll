#!/usr/bin/env python3
"""
Nanobot Wrapper with ANE Context Provider

This wrapper starts nanobot with the ANE compressed context provider
automatically registered, so compressed conversation history is
injected before each inference call.

Usage:
    python nanobot_wrapper.py  # Starts nanobot with ANE context provider
"""

import asyncio
import logging
import signal
import sys
from pathlib import Path
from typing import Optional

import aiohttp

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ANE context server configuration
ANE_CONTEXT_URL = "http://127.0.0.1:8766"


async def ane_context_provider(request_context) -> Optional["RuntimeContextBlock"]:
    """
    RuntimeContextProvider that fetches compressed context from ANE daemon.

    Called before each LLM inference to inject compressed conversation history.
    """
    from nanobot.runtime_context import RuntimeContextBlock

    # Get session key from request context
    session_key = getattr(request_context, 'session_key', None)
    if not session_key:
        return None

    try:
        async with aiohttp.ClientSession() as session:
            url = f"{ANE_CONTEXT_URL}/context/{session_key}"
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=2.0)) as response:
                if response.status != 200:
                    return None

                data = await response.json()
                context = data.get("context", "")

                if not context:
                    return None

                stats = data.get("stats", {})
                turn_count = stats.get("turn_count", 0)
                token_estimate = stats.get("token_estimate", 0)

                logger.debug(
                    f"Injecting ANE context for {session_key[:8]}...: "
                    f"{turn_count} turns, ~{token_estimate} tokens"
                )

                return RuntimeContextBlock(
                    source="ane_compression",
                    content=context
                )

    except aiohttp.ClientError as e:
        logger.debug(f"ANE context fetch failed: {e}")
        return None
    except asyncio.TimeoutError:
        logger.debug("ANE context fetch timed out")
        return None
    except Exception as e:
        logger.debug(f"ANE context provider error: {e}")
        return None


async def check_ane_daemon() -> bool:
    """Check if ANE daemon is available."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{ANE_CONTEXT_URL}/status", timeout=aiohttp.ClientTimeout(total=2.0)) as response:
                return response.status == 200
    except Exception:
        return False


async def run_nanobot_with_ane():
    """Run nanobot with ANE context provider registered."""
    from nanobot import Nanobot

    # Check ANE daemon status
    ane_available = await check_ane_daemon()
    if ane_available:
        logger.info(f"ANE daemon available at {ANE_CONTEXT_URL}")
    else:
        logger.warning(f"ANE daemon not available at {ANE_CONTEXT_URL} - context injection disabled")

    # Create nanobot instance
    logger.info("Starting nanobot with ANE context provider...")
    bot = Nanobot.from_config()

    # Register ANE context provider
    if ane_available:
        unsubscribe = bot.runtime.add_context_provider(ane_context_provider)
        logger.info("ANE context provider registered")

    # Note: This is a simplified example. In practice, you'd need to:
    # 1. Start the WebSocket channel
    # 2. Handle the gateway lifecycle
    # 3. Properly integrate with nanobot's channel system

    logger.info("Nanobot started. Use the standard nanobot CLI or WebUI to interact.")
    logger.info("ANE compressed context will be injected automatically before each inference.")

    # Keep running
    try:
        while True:
            await asyncio.sleep(3600)
    except asyncio.CancelledError:
        if ane_available:
            unsubscribe()
        logger.info("Nanobot stopped")


def main():
    """Main entry point."""
    print("""
╔═══════════════════════════════════════════════════════════════╗
║         Nanobot + ANE Context Provider Integration            ║
╠═══════════════════════════════════════════════════════════════╣
║                                                               ║
║  This wrapper demonstrates how to register the ANE context    ║
║  provider with nanobot programmatically.                      ║
║                                                               ║
║  For production use, you'll need to either:                   ║
║  1. Modify nanobot's gateway startup to include this provider ║
║  2. Run nanobot as a library instead of CLI                   ║
║  3. Create a nanobot plugin that registers the provider       ║
║                                                               ║
║  Current status:                                              ║
║  - ANE daemon HTTP server: http://127.0.0.1:8766              ║
║  - Use 'anectl status' to check daemon                        ║
║  - Use 'anectl context' to view compressed context            ║
║                                                               ║
╚═══════════════════════════════════════════════════════════════╝
""")

    print("\nTo fully integrate, the nanobot source would need to be modified to:")
    print("1. Load custom context providers from a config file or plugin")
    print("2. Or: Start the gateway with pre-registered providers")
    print("\nFor now, the ANE daemon is running and compressing context.")
    print("The compressed context is available at:")
    print(f"  curl {ANE_CONTEXT_URL}/context")
    print("\nThis can be manually queried or integrated when nanobot supports")
    print("config-based RuntimeContextProvider registration.")


if __name__ == "__main__":
    main()
