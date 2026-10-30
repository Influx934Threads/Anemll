"""
ANE Compression Service - Runs compression model on Apple Neural Engine

Handles:
- Phase 1: Turn compression (rolling session summaries)
- Phase 2: Tool result compression (on-demand)

Uses ANEInference for actual model execution on Apple Neural Engine.
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from datetime import datetime
import json

from .ane_inference import ANEInference

logger = logging.getLogger(__name__)


@dataclass
class CompressionMetrics:
    """Metrics for measuring compression benefit"""
    total_input_tokens: int = 0      # Original conversation tokens
    total_output_tokens: int = 0     # Compressed summary tokens
    total_turns_compressed: int = 0
    total_compression_time_ms: float = 0
    tool_compressions: int = 0
    tool_input_chars: int = 0
    tool_output_chars: int = 0

    @property
    def compression_ratio(self) -> float:
        """How much we're reducing (e.g., 5.0 = 5x reduction)"""
        if self.total_output_tokens == 0:
            return 0
        return self.total_input_tokens / self.total_output_tokens

    @property
    def tokens_saved(self) -> int:
        """Total tokens saved by compression"""
        return self.total_input_tokens - self.total_output_tokens

    @property
    def avg_compression_time_ms(self) -> float:
        """Average time per compression"""
        if self.total_turns_compressed == 0:
            return 0
        return self.total_compression_time_ms / self.total_turns_compressed


@dataclass
class SessionSummary:
    """Rolling summary for a session"""
    text: str = ""
    facts: list[dict] = field(default_factory=list)
    turn_count: int = 0
    last_updated: datetime = field(default_factory=datetime.now)
    token_estimate: int = 0
    input_tokens: int = 0  # Original tokens for this session


@dataclass
class CompressionTask:
    """Task for the compression queue"""
    session_key: str
    task_type: str  # "turn" or "tool"
    content: Any
    priority: int = 1  # Lower = higher priority
    created_at: datetime = field(default_factory=datetime.now)

    def __lt__(self, other):
        return self.priority < other.priority


class ANEService:
    """
    Unified ANE compression service.

    Runs a small model (Qwen3-1.7B) on Apple Neural Engine for:
    1. Continuous turn compression - maintains rolling session summaries
    2. Tool result compression - compresses large tool outputs on-demand
    """

    STATE_FILE = "~/.nanobot/run/ane_state.json"

    def __init__(
        self,
        model_path: str | Path,
        max_summary_tokens: int = 2000,
        tool_compression_threshold: int = 500,
    ):
        self.model_path = Path(model_path).expanduser()
        self.max_summary_tokens = max_summary_tokens
        self.tool_compression_threshold = tool_compression_threshold
        self.state_file = Path(self.STATE_FILE).expanduser()

        # Session summaries (Phase 1)
        self.session_summaries: dict[str, SessionSummary] = {}

        # Compression queue
        self.queue: asyncio.PriorityQueue[CompressionTask] = asyncio.PriorityQueue()

        # ANE inference engine
        self._inference: ANEInference | None = None
        self._running = False
        self._worker_task: asyncio.Task | None = None

        # Metrics tracking
        self.metrics = CompressionMetrics()

        # Track last processed position per session (for daemon)
        self._session_positions: dict[str, int] = {}

        # Load persisted state
        self._load_state()

    def _load_state(self):
        """Load persisted state from disk."""
        if not self.state_file.exists():
            logger.debug("No persisted state found")
            return

        try:
            with open(self.state_file) as f:
                data = json.load(f)

            # Restore session summaries
            for key, summary_data in data.get("sessions", {}).items():
                self.session_summaries[key] = SessionSummary(
                    text=summary_data.get("text", ""),
                    facts=summary_data.get("facts", []),
                    turn_count=summary_data.get("turn_count", 0),
                    token_estimate=summary_data.get("token_estimate", 0),
                    input_tokens=summary_data.get("input_tokens", 0),
                )

            # Restore metrics
            metrics_data = data.get("metrics", {})
            self.metrics.total_input_tokens = metrics_data.get("total_input_tokens", 0)
            self.metrics.total_output_tokens = metrics_data.get("total_output_tokens", 0)
            self.metrics.total_turns_compressed = metrics_data.get("total_turns_compressed", 0)
            self.metrics.total_compression_time_ms = metrics_data.get("total_compression_time_ms", 0)

            # Restore session positions
            self._session_positions = data.get("session_positions", {})

            logger.info(f"Loaded state: {len(self.session_summaries)} sessions, {self.metrics.total_turns_compressed} turns")
            for session_key, pos in self._session_positions.items():
                logger.info(f"  Session {session_key[:8]}...: position {pos}")

        except Exception as e:
            logger.warning(f"Failed to load state: {e}")

    def _save_state(self):
        """Persist state to disk."""
        try:
            self.state_file.parent.mkdir(parents=True, exist_ok=True)

            data = {
                "sessions": {
                    key: {
                        "text": summary.text,
                        "facts": summary.facts,
                        "turn_count": summary.turn_count,
                        "token_estimate": summary.token_estimate,
                        "input_tokens": summary.input_tokens,
                    }
                    for key, summary in self.session_summaries.items()
                },
                "metrics": {
                    "total_input_tokens": self.metrics.total_input_tokens,
                    "total_output_tokens": self.metrics.total_output_tokens,
                    "total_turns_compressed": self.metrics.total_turns_compressed,
                    "total_compression_time_ms": self.metrics.total_compression_time_ms,
                },
                "session_positions": self._session_positions if hasattr(self, '_session_positions') else {},
                "saved_at": datetime.now().isoformat(),
            }

            with open(self.state_file, "w") as f:
                json.dump(data, f, indent=2)

            logger.debug("State saved")

        except Exception as e:
            logger.warning(f"Failed to save state: {e}")

    async def start(self):
        """Initialize and start the ANE compression service"""
        logger.info(f"Starting ANE service with model: {self.model_path}")

        # Load model on ANE
        await self._load_model()

        # Start background worker
        self._running = True
        self._worker_task = asyncio.create_task(self._compression_worker())

        logger.info("ANE service started")

    async def stop(self):
        """Stop the ANE service"""
        self._running = False
        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass

        # Save state before stopping
        self._save_state()
        logger.info("ANE service stopped")

    async def _load_model(self):
        """Load the compression model on ANE"""
        meta_path = self.model_path / "meta.yaml"
        if not meta_path.exists():
            raise FileNotFoundError(f"Model meta.yaml not found at {meta_path}")

        # Initialize ANE inference engine
        self._inference = ANEInference(self.model_path)
        await self._inference.load()

        logger.info(f"ANE model loaded from {self.model_path}")

    async def _compression_worker(self):
        """Background worker that processes compression tasks"""
        logger.info("Compression worker started")

        while self._running:
            try:
                # Wait for task with timeout to allow checking _running
                try:
                    task = await asyncio.wait_for(
                        self.queue.get(),
                        timeout=1.0
                    )
                except asyncio.TimeoutError:
                    continue

                # Process the task
                if task.task_type == "turn":
                    await self._process_turn_compression(task)
                elif task.task_type == "tool":
                    await self._process_tool_compression(task)

                self.queue.task_done()

            except Exception as e:
                logger.error(f"Compression worker error: {e}")

    async def _process_turn_compression(self, task: CompressionTask):
        """Process a turn compression task (Phase 1)"""
        start_time = time.perf_counter()

        session_key = task.session_key
        turn = task.content  # list of messages (user + assistant)

        # Calculate input tokens (rough estimate: 1.3 tokens per word)
        input_text = " ".join([msg.get('content', '') for msg in turn])
        input_tokens = int(len(input_text.split()) * 1.3)

        # Extract key facts from the turn
        facts = await self._extract_facts(turn)

        # Get or create session summary
        summary = self.session_summaries.get(session_key, SessionSummary())

        # Merge new facts into summary
        summary.facts.extend(facts)
        summary.turn_count += 1
        summary.input_tokens += input_tokens
        summary.last_updated = datetime.now()

        # Regenerate summary text if needed
        if len(summary.facts) > 10 or summary.turn_count % 5 == 0:
            summary.text = await self._consolidate_facts(summary.facts)
            # Prune old facts after consolidation
            summary.facts = summary.facts[-5:]  # Keep recent for context

        # Estimate output tokens
        summary.token_estimate = int(len(summary.text.split()) * 1.3)

        self.session_summaries[session_key] = summary

        # Update metrics
        elapsed_ms = (time.perf_counter() - start_time) * 1000
        self.metrics.total_input_tokens += input_tokens
        self.metrics.total_output_tokens = sum(
            s.token_estimate for s in self.session_summaries.values()
        )
        self.metrics.total_turns_compressed += 1
        self.metrics.total_compression_time_ms += elapsed_ms

        logger.info(
            f"Compressed: {summary.turn_count} turns → ~{summary.token_estimate:.0f} tokens "
            f"(ratio: {self.metrics.compression_ratio:.1f}x, saved: {self.metrics.tokens_saved} tokens)"
        )

        # Persist state periodically (every 5 turns)
        if self.metrics.total_turns_compressed % 5 == 0:
            self._save_state()

    async def _process_tool_compression(self, task: CompressionTask):
        """Process a tool result compression task (Phase 2)"""
        # Tool compression is handled synchronously via compress_tool_result
        # This is for any async/queued tool compression if needed
        pass

    async def _extract_facts(self, turn: list[dict]) -> list[dict]:
        """Extract key facts from a conversation turn"""
        # Format the turn for the model
        turn_text = "\n".join([
            f"{msg.get('role', 'unknown')}: {msg.get('content', '')[:500]}"
            for msg in turn
        ])

        prompt = f"""Extract key facts from this conversation turn.
Output as JSON array of facts, each with "type" and "content".
Types: decision, preference, context, task, result

Turn:
{turn_text}

Facts (JSON array):"""

        # Run inference on ANE
        response = await self._generate(prompt, max_tokens=200)

        # Parse response
        try:
            # Try to extract JSON from response
            import re
            json_match = re.search(r'\[.*\]', response, re.DOTALL)
            if json_match:
                facts = json.loads(json_match.group())
                return facts
        except (json.JSONDecodeError, AttributeError):
            pass

        # Fallback: create a simple fact
        return [{"type": "context", "content": turn_text[:200]}]

    async def _consolidate_facts(self, facts: list[dict]) -> str:
        """Consolidate multiple facts into a coherent summary"""
        facts_text = "\n".join([
            f"- [{f.get('type', 'info')}] {f.get('content', '')}"
            for f in facts
        ])

        prompt = f"""Consolidate these facts into a brief summary paragraph.
Keep only the most important information. Be concise.

Facts:
{facts_text}

Summary:"""

        response = await self._generate(prompt, max_tokens=300)
        return response.strip()

    async def _generate(self, prompt: str, max_tokens: int = 100) -> str:
        """Generate text using the ANE model"""
        if self._inference is None:
            raise RuntimeError("ANE service not started - call start() first")

        # Use ANEInference for actual generation on Neural Engine
        return await self._inference.generate(
            prompt=prompt,
            max_tokens=max_tokens,
            temperature=0.3,  # Lower temperature for compression tasks
        )

    # ─── PUBLIC API ───

    async def queue_turn_compression(
        self,
        session_key: str,
        turn: list[dict],
        priority: int = 1
    ):
        """
        Queue a turn for background compression (Phase 1).

        Call this after each agent turn completes.
        Does not block - compression happens in background.
        """
        task = CompressionTask(
            session_key=session_key,
            task_type="turn",
            content=turn,
            priority=priority
        )
        await self.queue.put(task)
        logger.debug(f"Queued compression for {session_key}")

    async def compress_tool_result(self, content: str) -> str:
        """
        Compress a tool result immediately (Phase 2).

        Call this when a tool returns a large result.
        Blocks until compression is complete (but fast on ANE).

        Returns:
            Compressed content, or original if below threshold
        """
        # Skip small content
        if len(content) < self.tool_compression_threshold:
            return content

        prompt = f"""Compress this tool output to its essential information.
Keep key data, remove redundancy. Be concise but complete.

Tool output:
{content[:4000]}  # Limit input size

Compressed:"""

        compressed = await self._generate(prompt, max_tokens=500)

        # Sanity check - don't return if compression failed
        if len(compressed) < 10:
            return content

        original_len = len(content)
        compressed_len = len(compressed)
        ratio = compressed_len / original_len

        logger.debug(
            f"Tool result compressed: {original_len} -> {compressed_len} "
            f"({ratio:.1%})"
        )

        return compressed

    def get_session_context(self, session_key: str) -> str:
        """
        Get the current compressed context for a session (Phase 3).

        Call this from RuntimeContextProvider to inject into prompts.

        Returns:
            Compressed summary text, or empty string if none
        """
        summary = self.session_summaries.get(session_key)
        if summary and summary.text:
            return f"[Conversation History Summary]\n{summary.text}"
        return ""

    def get_session_stats(self, session_key: str) -> dict:
        """Get statistics for a session's compression state"""
        summary = self.session_summaries.get(session_key)
        if not summary:
            return {"exists": False}

        return {
            "exists": True,
            "turn_count": summary.turn_count,
            "token_estimate": summary.token_estimate,
            "input_tokens": summary.input_tokens,
            "fact_count": len(summary.facts),
            "last_updated": summary.last_updated.isoformat(),
        }

    def get_metrics(self) -> dict:
        """Get overall compression metrics"""
        return {
            "total_input_tokens": self.metrics.total_input_tokens,
            "total_output_tokens": self.metrics.total_output_tokens,
            "compression_ratio": round(self.metrics.compression_ratio, 2),
            "tokens_saved": self.metrics.tokens_saved,
            "turns_compressed": self.metrics.total_turns_compressed,
            "avg_compression_time_ms": round(self.metrics.avg_compression_time_ms, 1),
            "total_compression_time_ms": round(self.metrics.total_compression_time_ms, 1),
            "tool_compressions": self.metrics.tool_compressions,
            "active_sessions": len(self.session_summaries),
        }

    def get_session_position(self, session_key: str) -> int:
        """Get last processed position for a session."""
        return self._session_positions.get(session_key, -1)

    def set_session_position(self, session_key: str, position: int):
        """Set last processed position for a session."""
        self._session_positions[session_key] = position

    def reset_session_position(self, session_key: str, new_position: int):
        """Reset session position after database compaction."""
        old_pos = self._session_positions.get(session_key, -1)
        self._session_positions[session_key] = new_position
        logger.info(f"Reset session {session_key[:16]}... position: {old_pos} -> {new_position}")
