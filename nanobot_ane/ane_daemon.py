#!/usr/bin/env python3
"""
ANE Compression Daemon - Background service for nanobot context compression.

Runs independently of nanobot and connects via WebSocket to monitor
conversations and compress context using Apple Neural Engine.
"""

import asyncio
import json
import logging
import os
import signal
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

import websockets
from websockets.exceptions import ConnectionClosed
from aiohttp import web

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from nanobot_ane.service import ANEService
from nanobot_ane.ws_handler import NanobotWSHandler, ConversationTurn
from nanobot_ane.session_db import SessionDBReader

# Configuration
DEFAULT_MODEL_PATH = "~/Build/Anemll/models/qwen3-1.7b-ctx2048"
DEFAULT_WS_URL = "ws://127.0.0.1:8765"
DEFAULT_LOG_DIR = "~/.nanobot/logs"
DEFAULT_CONTEXT_PORT = 8766  # HTTP server for context injection
PID_FILE = "~/.nanobot/run/ane_daemon.pid"

# Setup logging
def setup_logging(log_dir: str, debug: bool = False):
    log_path = Path(log_dir).expanduser()
    log_path.mkdir(parents=True, exist_ok=True)

    log_file = log_path / "ane_daemon.log"

    level = logging.DEBUG if debug else logging.INFO

    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler(sys.stdout)
        ]
    )
    return logging.getLogger(__name__)


class ANEDaemon:
    """
    Background daemon that monitors nanobot conversations and
    compresses context using Apple Neural Engine.
    """

    def __init__(
        self,
        model_path: str = DEFAULT_MODEL_PATH,
        ws_url: str = DEFAULT_WS_URL,
        ws_token: str = "",
        context_port: int = DEFAULT_CONTEXT_PORT,
    ):
        self.model_path = Path(model_path).expanduser()
        self.ws_url = ws_url
        self.ws_token = ws_token
        self.context_port = context_port

        self.ane_service: Optional[ANEService] = None
        self.ws_connection = None
        self._running = False
        self._reconnect_delay = 1.0
        self._max_reconnect_delay = 30.0

        # HTTP server for context injection
        self._http_app: Optional[web.Application] = None
        self._http_runner: Optional[web.AppRunner] = None

        # SQLite database reader for fetching messages
        self.session_db = SessionDBReader()

        # WebSocket message handler
        self.ws_handler = NanobotWSHandler()
        self.ws_handler.on_turn_complete = self._on_turn_complete
        self.ws_handler.on_tool_result = self._on_tool_result
        self.ws_handler.on_session_updated = self._on_session_updated

        self.logger = logging.getLogger(__name__)

    async def start(self):
        """Start the daemon."""
        self.logger.info("Starting ANE Daemon...")
        self._running = True

        # Write PID file
        self._write_pid()

        # Start ANE service
        self.logger.info(f"Loading ANE model from {self.model_path}")
        self.ane_service = ANEService(self.model_path)
        await self.ane_service.start()
        self.logger.info("ANE service started")

        # Start HTTP context server
        await self._start_http_server()

        # Start session polling task (checks all sessions periodically)
        self._poll_task = asyncio.create_task(self._poll_all_sessions())

        # Connect to nanobot WebSocket
        await self._connect_loop()

    async def stop(self):
        """Stop the daemon."""
        self.logger.info("Stopping ANE Daemon...")
        self._running = False

        # Cancel polling task
        if hasattr(self, '_poll_task') and self._poll_task:
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass

        if self.ws_connection:
            await self.ws_connection.close()

        # Stop HTTP server
        await self._stop_http_server()

        if self.ane_service:
            await self.ane_service.stop()

        self._remove_pid()
        self.logger.info("ANE Daemon stopped")

    def _write_pid(self):
        """Write PID file for daemon management."""
        pid_path = Path(PID_FILE).expanduser()
        pid_path.parent.mkdir(parents=True, exist_ok=True)
        pid_path.write_text(str(os.getpid()))

    def _remove_pid(self):
        """Remove PID file."""
        pid_path = Path(PID_FILE).expanduser()
        if pid_path.exists():
            pid_path.unlink()

    # ─── HTTP Context Server ───

    async def _start_http_server(self):
        """Start the HTTP server for context injection."""
        self._http_app = web.Application()
        self._http_app.router.add_get("/context/{session_key}", self._handle_get_context)
        self._http_app.router.add_get("/context", self._handle_get_all_contexts)
        self._http_app.router.add_get("/status", self._handle_status)
        self._http_app.router.add_get("/metrics", self._handle_metrics)
        # Direct compression endpoint for nanobot integration
        self._http_app.router.add_post("/compress", self._handle_compress)

        self._http_runner = web.AppRunner(self._http_app)
        await self._http_runner.setup()

        site = web.TCPSite(self._http_runner, "127.0.0.1", self.context_port)
        await site.start()

        self.logger.info(f"Context server started at http://127.0.0.1:{self.context_port}")

    async def _stop_http_server(self):
        """Stop the HTTP server."""
        if self._http_runner:
            await self._http_runner.cleanup()
            self.logger.info("Context server stopped")

    async def _handle_get_context(self, request: web.Request) -> web.Response:
        """
        GET /context/{session_key}

        Returns the compressed context for a session.
        Nanobot can call this before each inference to get context.
        """
        session_key = request.match_info.get("session_key", "")

        if not self.ane_service:
            return web.json_response({"error": "ANE service not ready"}, status=503)

        context = self.ane_service.get_session_context(session_key)
        stats = self.ane_service.get_session_stats(session_key)

        return web.json_response({
            "session_key": session_key,
            "context": context,
            "stats": stats,
        })

    async def _handle_get_all_contexts(self, request: web.Request) -> web.Response:
        """
        GET /context

        Returns all available session contexts.
        """
        if not self.ane_service:
            return web.json_response({"error": "ANE service not ready"}, status=503)

        contexts = {}
        for session_key in self.ane_service.session_summaries:
            contexts[session_key] = {
                "context": self.ane_service.get_session_context(session_key),
                "stats": self.ane_service.get_session_stats(session_key),
            }

        return web.json_response({"sessions": contexts})

    async def _handle_status(self, request: web.Request) -> web.Response:
        """GET /status - Return daemon status."""
        return web.json_response(self.get_status())

    async def _handle_metrics(self, request: web.Request) -> web.Response:
        """GET /metrics - Return compression metrics."""
        if not self.ane_service:
            return web.json_response({"error": "ANE service not ready"}, status=503)
        return web.json_response(self.ane_service.get_metrics())

    async def _handle_compress(self, request: web.Request) -> web.Response:
        """
        POST /compress - Return pre-computed summary for nanobot integration.

        This endpoint returns the ALREADY COMPUTED summary from continuous
        background compression. It does NOT reprocess all messages on each call -
        the advantage of ANE is processing small bits continuously, not 40k
        context in one go.

        The continuous polling loop handles turn-by-turn compression in background.
        This endpoint just returns what's already been computed.

        Request body:
            {
                "session_key": str,
                "messages": list[dict],  # For reference only, not reprocessed
                "previous_summary": str | None  # Fallback if no ANE summary yet
            }

        Response:
            {
                "summary": str | None,  # Pre-computed summary (instant return)
                "stats": dict  # Session compression statistics
            }
        """
        if not self.ane_service:
            return web.json_response({"error": "ANE service not ready"}, status=503)

        try:
            data = await request.json()
            session_key = data.get("session_key")
            messages = data.get("messages", [])
            previous_summary = data.get("previous_summary")

            if not session_key:
                return web.json_response({"error": "session_key required"}, status=400)

            if not messages:
                return web.json_response({"error": "messages required"}, status=400)

            self.logger.info(
                f"Compress request for {session_key[:16]}...: {len(messages)} messages"
            )

            # Process messages through ANE compression
            summary = await self.ane_service.generate_summary_for_nanobot(
                session_key,
                messages,
                previous_summary,
            )

            stats = self.ane_service.get_session_stats(session_key)

            if summary:
                self.logger.info(
                    f"Compression complete for {session_key[:16]}...: "
                    f"{stats.get('turn_count', 0)} turns → {len(summary)} chars"
                )
            else:
                self.logger.warning(
                    f"Compression returned no summary for {session_key[:16]}..."
                )

            return web.json_response({
                "summary": summary,
                "stats": stats,
            })

        except json.JSONDecodeError as e:
            self.logger.error(f"Invalid JSON in compress request: {e}")
            return web.json_response({"error": f"Invalid JSON: {e}"}, status=400)
        except Exception as e:
            self.logger.error(f"Compression error: {e}", exc_info=True)
            return web.json_response({"error": str(e)}, status=500)

    # ─── WebSocket Connection ───

    async def _connect_loop(self):
        """Main connection loop with auto-reconnect."""
        while self._running:
            try:
                await self._connect_and_listen()
            except ConnectionClosed as e:
                self.logger.warning(f"WebSocket connection closed: {e}")
            except Exception as e:
                self.logger.error(f"WebSocket error: {e}")

            if self._running:
                self.logger.info(f"Reconnecting in {self._reconnect_delay}s...")
                await asyncio.sleep(self._reconnect_delay)
                self._reconnect_delay = min(
                    self._reconnect_delay * 2,
                    self._max_reconnect_delay
                )

    async def _connect_and_listen(self):
        """Connect to nanobot WebSocket and listen for messages."""
        # Build connection URL with token if provided
        url = self.ws_url
        if self.ws_token:
            url = f"{url}?token={self.ws_token}"

        self.logger.info(f"Connecting to nanobot at {self.ws_url}...")

        async with websockets.connect(url, ping_interval=60, ping_timeout=30) as ws:
            self.ws_connection = ws
            self._reconnect_delay = 1.0  # Reset on successful connect
            self.logger.info("Connected to nanobot WebSocket")

            async for message in ws:
                await self._handle_message(message)

    async def _handle_message(self, raw_message: str):
        """Handle incoming WebSocket message from nanobot."""
        # Debug: log all incoming messages
        self.logger.debug(f"WS message received: {raw_message[:500]}")

        # Delegate to handler
        result = self.ws_handler.handle_message(raw_message)
        if result:
            self.logger.debug(f"Parsed message type: {result.get('type', 'unknown')}")

    def _on_turn_complete(self, session_key: str, turn: ConversationTurn):
        """Callback when a conversation turn is complete."""
        if not self.ane_service:
            return

        # Queue for compression
        turn_data = [
            {"role": "user", "content": turn.user_content},
            {"role": "assistant", "content": turn.assistant_content}
        ]

        # Schedule async task
        asyncio.create_task(self._queue_compression(session_key, turn_data))

    async def _queue_compression(self, session_key: str, turn_data: list):
        """Queue a turn for compression."""
        await self.ane_service.queue_turn_compression(session_key, turn_data)

    def _on_tool_result(self, session_key: str, result: str):
        """Callback when a large tool result is received."""
        if not self.ane_service:
            return

        # Schedule async compression
        asyncio.create_task(self._compress_tool_result(session_key, result))

    def _on_session_updated(self, chat_id: str):
        """Callback when a session is updated - fetch messages from SQLite."""
        asyncio.create_task(self._fetch_and_process_messages(chat_id))

    async def _fetch_and_process_messages(self, chat_id: str):
        """Fetch messages from nanobot SQLite database and process for compression."""
        try:
            # Check max position first (runs in thread pool to not block)
            import asyncio
            curr_max_pos = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self.session_db.get_max_position(chat_id)
            )

            # Use service's persisted position tracking
            prev_max_pos = self.ane_service.get_session_position(chat_id)
            self.logger.info(f"Position check: prev={prev_max_pos}, curr={curr_max_pos}")

            if curr_max_pos <= prev_max_pos:
                self.logger.debug(f"No new messages (already at pos {curr_max_pos})")
                return

            self.ane_service.set_session_position(chat_id, curr_max_pos)
            self.logger.info(f"Processing messages from pos {prev_max_pos} to {curr_max_pos}")

            # Read recent messages from SQLite (after last seen position)
            messages = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self.session_db.get_session_messages(chat_id, limit=50, after_position=prev_max_pos)
            )

            if not messages:
                self.logger.debug(f"No user/assistant messages for chat {chat_id[:8]}...")
                return

            self.logger.debug(f"Chat {chat_id[:8]}...: {len(messages)} user/assistant messages")

            # Feed messages to handler for turn detection
            session = self.ws_handler.get_or_create_session(chat_id)
            if session:
                # Sync ws_handler state with service's persisted state
                service_stats = self.ane_service.get_session_stats(chat_id)
                if service_stats.get("exists") and session.last_compressed_index == 0:
                    # Service has already compressed turns - skip re-detection
                    persisted_turns = service_stats.get("turn_count", 0)
                    if persisted_turns > 0:
                        self.logger.info(f"Resuming from {persisted_turns} previously compressed turns")
                        # Set index to skip re-detecting already compressed content
                        session.last_compressed_index = len(session.messages)

                added = 0
                # Update session messages from database
                for msg in messages:
                    role = msg.get("role", "")
                    content = msg.get("content", "")
                    if role and content:
                        # Check if already in session by position
                        pos = msg.get("position", -1)
                        existing = [m for m in session.messages if m.get("position") == pos]
                        if not existing:
                            session.messages.append({
                                "role": role,
                                "content": content,
                                "position": pos
                            })
                            added += 1
                            self.logger.debug(f"  Added {role} message (pos {pos}): {content[:50]}...")

                self.logger.debug(f"Session has {len(session.messages)} messages, last_compressed_index={session.last_compressed_index}")

                # Check for complete turns
                self.ws_handler._check_for_complete_turn(session)

        except Exception as e:
            self.logger.error(f"Error fetching messages for {chat_id}: {e}")

    async def _compress_tool_result(self, session_key: str, result: str):
        """Compress a large tool result."""
        compressed = await self.ane_service.compress_tool_result(result)
        self.logger.info(
            f"Compressed tool result for {session_key}: "
            f"{len(result)} -> {len(compressed)} chars"
        )

    async def _poll_all_sessions(self):
        """Periodically poll all active sessions for new messages."""
        poll_interval = 10  # seconds
        self.logger.info(f"Session polling started (every {poll_interval}s)")

        while self._running:
            try:
                await asyncio.sleep(poll_interval)
                if not self._running:
                    break

                # Get all active sessions from database (run in thread pool)
                loop = asyncio.get_event_loop()
                sessions = await loop.run_in_executor(
                    None,
                    lambda: self.session_db.get_active_sessions_with_positions(limit=10)
                )

                if not sessions:
                    self.logger.debug("No active sessions found in database")
                    continue

                for sess in sessions:
                    chat_id = sess['chat_id']
                    curr_max_pos = sess['max_pos']

                    # Check against our tracked position
                    prev_max_pos = self.ane_service.get_session_position(chat_id)

                    if curr_max_pos > prev_max_pos:
                        self.logger.info(f"Polling: new messages in {chat_id[:16]}... ({prev_max_pos} -> {curr_max_pos})")
                        await self._fetch_and_process_messages(chat_id)
                    elif prev_max_pos > 0 and curr_max_pos < prev_max_pos:
                        # Database was compacted - reset our tracking
                        self.logger.info(f"Polling: DB compacted for {chat_id[:16]}... (was {prev_max_pos}, now {curr_max_pos})")
                        self.ane_service.reset_session_position(chat_id, curr_max_pos)

            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Polling error: {e}")

        self.logger.info("Session polling stopped")

    def get_status(self) -> dict:
        """Get daemon status."""
        ws_stats = self.ws_handler.get_stats()
        metrics = self.ane_service.get_metrics() if self.ane_service else {}
        # Check WebSocket connection status (websockets library uses 'state' not 'closed')
        ws_connected = False
        if self.ws_connection is not None:
            try:
                ws_connected = self.ws_connection.state.name == "OPEN"
            except Exception:
                ws_connected = False
        return {
            "running": self._running,
            "connected": ws_connected,
            "model_path": str(self.model_path),
            "context_server": f"http://127.0.0.1:{self.context_port}",
            "ane_service": self.ane_service is not None,
            **ws_stats,  # active_sessions, total_turns, compressed_turns, pending_turns
            "metrics": metrics,
        }


async def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="ANE Compression Daemon")
    parser.add_argument("--model", default=DEFAULT_MODEL_PATH,
                        help="Path to ANE model")
    parser.add_argument("--ws-url", default=DEFAULT_WS_URL,
                        help="Nanobot WebSocket URL")
    parser.add_argument("--ws-token", default="",
                        help="WebSocket authentication token")
    parser.add_argument("--context-port", type=int, default=DEFAULT_CONTEXT_PORT,
                        help=f"HTTP port for context server (default: {DEFAULT_CONTEXT_PORT})")
    parser.add_argument("--log-dir", default=DEFAULT_LOG_DIR,
                        help="Log directory")
    parser.add_argument("--debug", action="store_true",
                        help="Enable debug logging")
    parser.add_argument("--foreground", "-f", action="store_true",
                        help="Run in foreground (don't daemonize)")

    args = parser.parse_args()

    logger = setup_logging(args.log_dir, args.debug)

    daemon = ANEDaemon(
        model_path=args.model,
        ws_url=args.ws_url,
        ws_token=args.ws_token,
        context_port=args.context_port,
    )

    # Handle signals
    def signal_handler(sig, frame):
        logger.info(f"Received signal {sig}")
        asyncio.create_task(daemon.stop())

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        await daemon.start()
    except KeyboardInterrupt:
        pass
    finally:
        await daemon.stop()


if __name__ == "__main__":
    asyncio.run(main())
