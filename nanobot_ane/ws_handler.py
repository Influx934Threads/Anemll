"""
WebSocket Message Handler - Parses nanobot WebSocket messages.

Handles the various message types from nanobot's WebSocket API
and extracts conversation data for compression.
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


@dataclass
class ConversationTurn:
    """A single conversation turn (user + assistant)."""
    user_content: str
    assistant_content: str
    timestamp: datetime = field(default_factory=datetime.now)
    session_key: str = ""
    compressed: bool = False


@dataclass
class SessionState:
    """Tracks state for a conversation session."""
    session_key: str
    messages: list[dict] = field(default_factory=list)
    turns: list[ConversationTurn] = field(default_factory=list)
    last_compressed_index: int = 0
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)


class NanobotWSHandler:
    """
    Handles WebSocket messages from nanobot.

    Parses different message types and tracks conversation state
    for compression purposes.
    """

    # Message type constants
    MSG_USER = "user_message"
    MSG_ASSISTANT = "assistant_message"
    MSG_STREAM = "stream"
    MSG_STREAM_END = "stream_end"
    MSG_TOOL_CALL = "tool_call"
    MSG_TOOL_RESULT = "tool_result"
    MSG_ERROR = "error"

    def __init__(self):
        self._sessions: dict[str, SessionState] = {}
        self._current_stream: dict[str, str] = {}  # session_key -> accumulated content

        # Callbacks
        self.on_turn_complete: Optional[Callable[[str, ConversationTurn], None]] = None
        self.on_tool_result: Optional[Callable[[str, str], None]] = None
        self.on_session_updated: Optional[Callable[[str], None]] = None  # session_key

    def handle_message(self, raw_message: str) -> Optional[dict]:
        """
        Parse and handle a raw WebSocket message.

        Returns the parsed message dict or None if parsing failed.
        """
        try:
            msg = json.loads(raw_message)
            self._process_message(msg)
            return msg
        except json.JSONDecodeError:
            logger.debug(f"Non-JSON message received: {raw_message[:100]}")
            return None
        except Exception as e:
            logger.error(f"Error handling message: {e}")
            return None

    def _process_message(self, msg: dict):
        """Process a parsed message based on its type."""
        # Nanobot uses "event" field for WebSocket notifications
        msg_type = msg.get("type") or msg.get("event", "")

        # Extract session key from various possible locations
        session_key = (
            msg.get("session_key") or
            msg.get("chat_id") or
            msg.get("metadata", {}).get("session_key") or
            "default"
        )

        # Ensure session exists
        if session_key not in self._sessions:
            self._sessions[session_key] = SessionState(session_key=session_key)

        session = self._sessions[session_key]
        session.updated_at = datetime.now()

        # Handle by message type/event
        if msg_type in ("message", "user_message"):
            self._handle_user_message(session, msg)
        elif msg_type in ("response", "assistant_message"):
            self._handle_assistant_message(session, msg)
        elif msg_type == "stream":
            self._handle_stream(session, msg)
        elif msg_type == "stream_end":
            self._handle_stream_end(session, msg)
        elif msg_type == "tool_result":
            self._handle_tool_result(session, msg)
        elif msg_type == "turn_complete":
            self._handle_turn_complete(session, msg)
        elif msg_type == "session_updated":
            # Nanobot event: session was updated, need to fetch messages via REST
            self._handle_session_updated(session, msg)
        elif msg_type == "progress":
            # Progress updates - just log
            pass
        else:
            logger.debug(f"Unhandled message type: {msg_type}")

    def _handle_user_message(self, session: SessionState, msg: dict):
        """Handle user message."""
        content = self._extract_content(msg)
        if content:
            session.messages.append({
                "role": "user",
                "content": content,
                "timestamp": datetime.now().isoformat()
            })
            logger.debug(f"User message in {session.session_key}: {content[:50]}...")

    def _handle_assistant_message(self, session: SessionState, msg: dict):
        """Handle assistant message."""
        content = self._extract_content(msg)
        if content:
            session.messages.append({
                "role": "assistant",
                "content": content,
                "timestamp": datetime.now().isoformat()
            })
            logger.debug(f"Assistant message in {session.session_key}: {content[:50]}...")

            # Check if we have a complete turn
            self._check_for_complete_turn(session)

    def _handle_stream(self, session: SessionState, msg: dict):
        """Handle streaming token."""
        delta = msg.get("delta", "") or msg.get("content", "")
        if delta:
            key = session.session_key
            self._current_stream[key] = self._current_stream.get(key, "") + delta

    def _handle_stream_end(self, session: SessionState, msg: dict):
        """Handle end of stream - finalize assistant message."""
        key = session.session_key
        if key in self._current_stream:
            content = self._current_stream.pop(key)
            if content:
                session.messages.append({
                    "role": "assistant",
                    "content": content,
                    "timestamp": datetime.now().isoformat()
                })
                logger.debug(f"Stream complete in {key}: {len(content)} chars")
                self._check_for_complete_turn(session)

    def _handle_tool_result(self, session: SessionState, msg: dict):
        """Handle tool execution result."""
        result = msg.get("result", "") or msg.get("content", "")
        tool_name = msg.get("tool_name", "") or msg.get("name", "unknown")

        if result and len(result) > 500 and self.on_tool_result:
            # Large tool result - queue for compression
            logger.debug(f"Large tool result from {tool_name}: {len(result)} chars")
            self.on_tool_result(session.session_key, result)

    def _handle_turn_complete(self, session: SessionState, msg: dict):
        """Handle explicit turn completion signal."""
        self._check_for_complete_turn(session)

    def _handle_session_updated(self, session: SessionState, msg: dict):
        """Handle session_updated event from nanobot."""
        # Don't log here - let the daemon log only when new turns are found
        if self.on_session_updated:
            self.on_session_updated(session.session_key)

    def _check_for_complete_turn(self, session: SessionState):
        """Check if we have a complete user+assistant turn to compress."""
        messages = session.messages
        last_idx = session.last_compressed_index

        # Look for user+assistant pairs starting from last compressed
        i = last_idx
        while i + 1 < len(messages):
            if (messages[i].get("role") == "user" and
                messages[i + 1].get("role") == "assistant"):

                turn = ConversationTurn(
                    user_content=messages[i]["content"],
                    assistant_content=messages[i + 1]["content"],
                    session_key=session.session_key,
                )
                session.turns.append(turn)
                session.last_compressed_index = i + 2

                # Notify callback
                if self.on_turn_complete:
                    self.on_turn_complete(session.session_key, turn)

                logger.debug(f"Turn ready for compression (session-local #{len(session.turns)})")
                i += 2
            else:
                i += 1

    def _extract_content(self, msg: dict) -> str:
        """Extract text content from a message."""
        content = msg.get("content")

        if isinstance(content, str):
            return content

        if isinstance(content, list):
            # Handle multimodal content
            texts = []
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    texts.append(block.get("text", ""))
                elif isinstance(block, str):
                    texts.append(block)
            return "\n".join(texts)

        return ""

    def get_session(self, session_key: str) -> Optional[SessionState]:
        """Get session state by key."""
        return self._sessions.get(session_key)

    def get_or_create_session(self, session_key: str) -> SessionState:
        """Get or create a session state by key."""
        if session_key not in self._sessions:
            self._sessions[session_key] = SessionState(session_key=session_key)
            logger.debug(f"Created ws_handler session tracking: {session_key[:16]}...")
        return self._sessions[session_key]

    def get_uncompressed_turns(self, session_key: str) -> list[ConversationTurn]:
        """Get turns that haven't been compressed yet."""
        session = self._sessions.get(session_key)
        if not session:
            return []
        return [t for t in session.turns if not t.compressed]

    def mark_turn_compressed(self, session_key: str, turn_index: int):
        """Mark a turn as compressed."""
        session = self._sessions.get(session_key)
        if session and turn_index < len(session.turns):
            session.turns[turn_index].compressed = True

    def clear_session(self, session_key: str):
        """Clear a session's state."""
        if session_key in self._sessions:
            del self._sessions[session_key]
            logger.debug(f"Cleared ws_handler session tracking: {session_key[:16]}...")

    def get_stats(self) -> dict:
        """Get handler statistics."""
        total_turns = sum(len(s.turns) for s in self._sessions.values())
        compressed = sum(
            sum(1 for t in s.turns if t.compressed)
            for s in self._sessions.values()
        )
        return {
            "active_sessions": len(self._sessions),
            "total_turns": total_turns,
            "compressed_turns": compressed,
            "pending_turns": total_turns - compressed,
        }
