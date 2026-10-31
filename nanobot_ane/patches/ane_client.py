"""ANE compression client for nanobot integration.

This client communicates with the ANE daemon to request compression
of conversation history. It's used by MemoryArchiver to try ANE
compression before falling back to native LLM summarization.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

logger = logging.getLogger(__name__)

ANE_SERVICE_URL = "http://127.0.0.1:8766"
ANE_AVAILABILITY_CACHE_SECONDS = 30.0


class ANEClient:
    """Client for communicating with the ANE compression service."""

    def __init__(self, base_url: str = ANE_SERVICE_URL):
        self.base_url = base_url.rstrip("/")
        self._available: bool | None = None
        self._last_check: float = 0

    async def is_available(self, force_check: bool = False) -> bool:
        """Check if ANE service is running.

        Caches result for ANE_AVAILABILITY_CACHE_SECONDS to avoid
        repeated connection attempts when service is down.
        """
        import time

        now = time.monotonic()
        if (
            not force_check
            and self._available is not None
            and (now - self._last_check) < ANE_AVAILABILITY_CACHE_SECONDS
        ):
            return self._available

        try:
            import aiohttp

            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.base_url}/status",
                    timeout=aiohttp.ClientTimeout(total=2.0),
                ) as resp:
                    self._available = resp.status == 200
                    if self._available:
                        data = await resp.json()
                        logger.debug("ANE service available: %s", data)
        except ImportError:
            logger.debug("aiohttp not available, ANE client disabled")
            self._available = False
        except asyncio.TimeoutError:
            logger.debug("ANE service check timed out")
            self._available = False
        except Exception as e:
            logger.debug("ANE service check failed: %s", e)
            self._available = False

        self._last_check = now
        return self._available

    async def compress_session(
        self,
        session_key: str,
        messages: list[dict[str, Any]],
        previous_summary: str | None = None,
    ) -> str | None:
        """Request ANE to compress messages and return the summary.

        This is the key integration point - nanobot sends messages,
        ANE compresses them and returns a summary that can be used
        as the session's archived context.

        Args:
            session_key: Unique session identifier
            messages: List of message dicts to compress
            previous_summary: Optional previous summary for continuity

        Returns:
            Compressed summary text, or None if compression failed
        """
        if not await self.is_available():
            return None

        try:
            import aiohttp

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}/compress",
                    json={
                        "session_key": session_key,
                        "messages": messages,
                        "previous_summary": previous_summary,
                    },
                    timeout=aiohttp.ClientTimeout(total=60.0),
                ) as resp:
                    if resp.status != 200:
                        error_text = await resp.text()
                        logger.warning(
                            "ANE compression failed for %s: %s %s",
                            session_key,
                            resp.status,
                            error_text[:200],
                        )
                        return None

                    data = await resp.json()
                    summary = data.get("summary")

                    if summary:
                        stats = data.get("stats", {})
                        logger.info(
                            "ANE compressed %s: %d turns → %d tokens",
                            session_key[:16],
                            stats.get("turn_count", 0),
                            stats.get("token_estimate", 0),
                        )
                    return summary

        except asyncio.TimeoutError:
            logger.warning("ANE compression timed out for %s", session_key)
            return None
        except Exception as e:
            logger.warning("ANE compression error for %s: %s", session_key, e)
            return None

    async def get_summary(self, session_key: str) -> str | None:
        """Get existing compressed summary for a session.

        This retrieves a pre-computed summary without triggering
        new compression. Useful for checking what ANE has ready.
        """
        if not await self.is_available():
            return None

        try:
            import aiohttp

            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.base_url}/context/{session_key}",
                    timeout=aiohttp.ClientTimeout(total=5.0),
                ) as resp:
                    if resp.status != 200:
                        return None
                    data = await resp.json()
                    return data.get("context") or None
        except Exception as e:
            logger.debug("Failed to get ANE summary for %s: %s", session_key, e)
            return None

    def invalidate(self) -> None:
        """Reset availability check for retry."""
        self._available = None
        self._last_check = 0


# Global client instance for convenience
_default_client: ANEClient | None = None


def get_ane_client() -> ANEClient:
    """Get the default ANE client instance."""
    global _default_client
    if _default_client is None:
        _default_client = ANEClient()
    return _default_client
