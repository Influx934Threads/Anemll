"""
Nanobot hook to compress tool outputs before storage using ANE.

This reduces context consumption by compressing large tool results
(file contents, command outputs, etc.) before they're stored in the database.
"""

import aiohttp
import logging

logger = logging.getLogger(__name__)

ANE_DAEMON_URL = "http://127.0.0.1:8766"
TOOL_COMPRESSION_THRESHOLD = 1000  # Compress outputs > 1000 chars


async def compress_tool_output(tool_result: str) -> str:
    """
    Compress tool output using ANE daemon before storing in database.

    Called by nanobot before storing tool results.
    Falls back to original if ANE unavailable or compression fails.
    """
    # Skip small outputs
    if len(tool_result) < TOOL_COMPRESSION_THRESHOLD:
        return tool_result

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{ANE_DAEMON_URL}/compress_tool",
                json={"content": tool_result},
                timeout=aiohttp.ClientTimeout(total=5.0)
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    compressed = data.get("compressed", tool_result)

                    compression_ratio = len(tool_result) / len(compressed) if compressed else 1.0
                    logger.info(
                        f"Compressed tool output: {len(tool_result)} → {len(compressed)} chars "
                        f"({compression_ratio:.1f}x)"
                    )
                    return compressed
                else:
                    logger.warning(f"Tool compression failed: HTTP {response.status}")
                    return tool_result

    except Exception as e:
        logger.debug(f"Tool compression unavailable: {e}")
        return tool_result


# Hook function for nanobot
async def pre_store_tool_result(result: dict) -> dict:
    """
    Nanobot hook called before storing tool results.

    Compresses large outputs to save context tokens.
    """
    if "content" in result and isinstance(result["content"], str):
        result["content"] = await compress_tool_output(result["content"])

    return result
