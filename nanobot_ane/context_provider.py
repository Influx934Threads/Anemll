"""
ANE Context Provider - Injects compressed context into nanobot prompts

This is Phase 3: The delivery mechanism that makes compressed history
available to the GPU model before each inference call.
"""

import logging
from typing import TYPE_CHECKING, Callable, Awaitable, Any
from dataclasses import dataclass

if TYPE_CHECKING:
    from .service import ANEService

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RuntimeContextBlock:
    """
    A block of context to be injected into the prompt.

    Matches nanobot's RuntimeContextBlock interface.
    """
    source: str
    content: str


def create_ane_context_provider(
    ane_service: "ANEService",
    max_tokens: int = 2000,
    include_stats: bool = False,
) -> Callable[[Any], Awaitable[RuntimeContextBlock | None]]:
    """
    Create a RuntimeContextProvider that injects ANE-compressed context.

    This provider is called before each LLM inference to provide
    additional context from the ANE compression service.

    Args:
        ane_service: The ANE service instance
        max_tokens: Maximum tokens for injected context
        include_stats: Whether to include compression statistics

    Returns:
        A provider function compatible with nanobot's RuntimeContextProvider

    Usage:
        ane_service = ANEService(...)
        provider = create_ane_context_provider(ane_service)

        # Register with nanobot's runtime context system
        runtime_context_providers = [provider]
    """

    async def ane_context_provider(request_context) -> RuntimeContextBlock | None:
        """
        Provide ANE-compressed context for the current request.

        Called by nanobot before each LLM inference.
        """
        # Get session key from request context
        session_key = getattr(request_context, 'session_key', None)

        if not session_key:
            logger.debug("No session_key in request context, skipping ANE context")
            return None

        # Get compressed context from ANE service
        compressed_context = ane_service.get_session_context(session_key)

        if not compressed_context:
            logger.debug(f"No compressed context for session {session_key}")
            return None

        # Optionally add stats
        if include_stats:
            stats = ane_service.get_session_stats(session_key)
            stats_line = (
                f"\n[Compression: {stats.get('turn_count', 0)} turns, "
                f"~{stats.get('token_estimate', 0):.0f} tokens]"
            )
            compressed_context += stats_line

        # Truncate if too long (rough token estimate)
        estimated_tokens = len(compressed_context.split()) * 1.3
        if estimated_tokens > max_tokens:
            # Truncate to fit
            words = compressed_context.split()
            max_words = int(max_tokens / 1.3)
            compressed_context = ' '.join(words[:max_words]) + "..."
            logger.debug(
                f"Truncated ANE context from {len(words)} to {max_words} words"
            )

        logger.debug(
            f"Injecting ANE context for {session_key}: "
            f"{len(compressed_context)} chars"
        )

        return RuntimeContextBlock(
            source="ane_compression",
            content=compressed_context
        )

    return ane_context_provider


# Convenience alias for simple usage
async def ane_context_provider(
    request_context,
    ane_service: "ANEService"
) -> RuntimeContextBlock | None:
    """
    Simple context provider function.

    For more control, use create_ane_context_provider() instead.
    """
    provider = create_ane_context_provider(ane_service)
    return await provider(request_context)


class ANEContextManager:
    """
    Manager for ANE context injection with additional features.

    Provides:
    - Context caching
    - Priority-based context selection
    - Context freshness tracking
    """

    def __init__(self, ane_service: "ANEService"):
        self.ane = ane_service
        self._context_cache: dict[str, tuple[str, float]] = {}

    async def get_context(
        self,
        session_key: str,
        max_age_seconds: float = 30.0
    ) -> str | None:
        """
        Get context with caching.

        Args:
            session_key: Session to get context for
            max_age_seconds: Maximum age of cached context

        Returns:
            Compressed context or None
        """
        import time

        # Check cache
        if session_key in self._context_cache:
            cached_content, cached_time = self._context_cache[session_key]
            if time.time() - cached_time < max_age_seconds:
                return cached_content

        # Get fresh context
        context = self.ane.get_session_context(session_key)

        if context:
            self._context_cache[session_key] = (context, time.time())

        return context

    def invalidate_cache(self, session_key: str | None = None):
        """
        Invalidate cached context.

        Args:
            session_key: Specific session to invalidate, or None for all
        """
        if session_key:
            self._context_cache.pop(session_key, None)
        else:
            self._context_cache.clear()

    def create_provider(self) -> Callable[[Any], Awaitable[RuntimeContextBlock | None]]:
        """Create a RuntimeContextProvider using this manager"""

        async def provider(request_context) -> RuntimeContextBlock | None:
            session_key = getattr(request_context, 'session_key', None)
            if not session_key:
                return None

            context = await self.get_context(session_key)
            if not context:
                return None

            return RuntimeContextBlock(
                source="ane_compression",
                content=context
            )

        return provider
