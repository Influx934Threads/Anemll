"""
ANE Hook - Integrates ANE compression into nanobot's agent lifecycle

Hooks into:
- before_iteration: Queue previous turn for compression while GPU thinks
- after_run: Queue final turn for compression
- Tool execution: Compress large tool results before they enter context
"""

import asyncio
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .service import ANEService

logger = logging.getLogger(__name__)


class ANEHook:
    """
    Nanobot AgentHook that integrates ANE compression.

    This hook:
    1. Queues turns for background compression during GPU inference (Phase 1)
    2. Can compress tool results before they bloat context (Phase 2)

    Usage:
        ane_service = ANEService(model_path="./models/qwen3-1.7b")
        await ane_service.start()

        hook = ANEHook(ane_service)
        result = await bot.run("...", hooks=[hook])
    """

    def __init__(
        self,
        ane_service: "ANEService",
        compress_tool_results: bool = True,
        min_turns_before_compression: int = 3,
    ):
        self.ane = ane_service
        self.compress_tool_results = compress_tool_results
        self.min_turns_before_compression = min_turns_before_compression

        # Track what we've already queued to avoid duplicates
        self._queued_turn_indices: dict[str, int] = {}

    def wants_streaming(self) -> bool:
        """We want streaming to monitor progress"""
        return True

    async def before_iteration(self, context) -> None:
        """
        Called before each LLM call.

        This is the perfect time to queue compression work because:
        - GPU is about to be busy for 10-30 seconds
        - ANE can work in parallel during this time
        """
        session_key = getattr(context, 'session_key', None)
        if not session_key:
            return

        messages = getattr(context, 'messages', [])

        # Don't compress until we have enough turns
        if len(messages) < self.min_turns_before_compression * 2:
            return

        # Find the last turn we haven't queued yet
        last_queued = self._queued_turn_indices.get(session_key, 0)

        # Queue any unprocessed turns (except current)
        # Messages are [user, assistant, user, assistant, ..., current_user]
        # We want to compress pairs: (user, assistant)
        turns_to_process = []
        i = last_queued

        while i < len(messages) - 2:  # Don't process current turn
            if i + 1 < len(messages):
                user_msg = messages[i]
                assistant_msg = messages[i + 1]

                # Only process user->assistant pairs
                if (user_msg.get('role') == 'user' and
                    assistant_msg.get('role') == 'assistant'):
                    turns_to_process.append([user_msg, assistant_msg])
                    i += 2
                else:
                    i += 1
            else:
                break

        # Queue turns for compression
        for turn in turns_to_process:
            await self.ane.queue_turn_compression(session_key, turn)
            self._queued_turn_indices[session_key] = i

        if turns_to_process:
            logger.debug(
                f"Queued {len(turns_to_process)} turns for ANE compression "
                f"(session: {session_key})"
            )

    async def on_stream(self, context, delta: str) -> None:
        """Called on each streaming delta - can monitor output freshness"""
        # Could track output rate, trigger re-compression if model is slow
        pass

    async def on_stream_end(self, context, resuming: bool) -> None:
        """Called when streaming ends"""
        pass

    async def after_iteration(self, context) -> None:
        """Called after each iteration (LLM call + tool execution)"""
        # Could collect intermediate results here if needed
        pass

    async def after_run(self, context) -> None:
        """
        Called after the agent run completes.

        Queue the final turn for compression.
        """
        session_key = getattr(context, 'session_key', None)
        messages = getattr(context, 'messages', [])

        if not session_key or len(messages) < 2:
            return

        # Queue the final turn (last user + assistant pair)
        final_turn = messages[-2:]
        if (len(final_turn) == 2 and
            final_turn[0].get('role') == 'user' and
            final_turn[1].get('role') == 'assistant'):

            await self.ane.queue_turn_compression(
                session_key,
                final_turn,
                priority=2  # Lower priority than mid-conversation compression
            )
            logger.debug(f"Queued final turn for ANE compression (session: {session_key})")

    async def before_run(self, context) -> None:
        """Called before the agent run starts"""
        pass

    async def on_error(self, context) -> None:
        """Called on error"""
        pass

    async def on_finally(self, context) -> None:
        """Called after run completes (success or error)"""
        pass

    # ─── TOOL RESULT COMPRESSION ───

    async def compress_tool_result(self, result: str) -> str:
        """
        Compress a tool result using ANE (Phase 2).

        This can be called from a custom tool wrapper or
        integrated into the tool execution pipeline.

        Args:
            result: Raw tool output

        Returns:
            Compressed result (or original if small/compression disabled)
        """
        if not self.compress_tool_results:
            return result

        return await self.ane.compress_tool_result(result)


class ANEToolWrapper:
    """
    Wrapper for tools that automatically compresses large outputs.

    Usage:
        original_tool = ReadFileTool()
        wrapped_tool = ANEToolWrapper(original_tool, ane_hook)

        # Tool results are automatically compressed
        result = await wrapped_tool.execute(path="large_file.py")
    """

    def __init__(self, tool, ane_hook: ANEHook):
        self.tool = tool
        self.ane_hook = ane_hook

    async def execute(self, **kwargs):
        """Execute tool and compress result if large"""
        result = await self.tool.execute(**kwargs)

        if isinstance(result, str) and len(result) > 500:
            return await self.ane_hook.compress_tool_result(result)

        return result

    def __getattr__(self, name):
        """Proxy other attributes to wrapped tool"""
        return getattr(self.tool, name)
