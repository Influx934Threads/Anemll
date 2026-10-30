"""
Session Database Reader - Reads nanobot session data from SQLite.

Provides direct access to nanobot's session storage for reading
conversation messages without needing the REST API.
"""

import json
import logging
import sqlite3
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Default nanobot sessions directory
DEFAULT_SESSIONS_DIR = "~/.nanobot/sessions"


class SessionDBReader:
    """
    Reads session data directly from nanobot's SQLite database.
    """

    def __init__(self, sessions_dir: str = DEFAULT_SESSIONS_DIR):
        self.sessions_dir = Path(sessions_dir).expanduser()
        self._db_path: Optional[Path] = None

    def _find_db(self) -> Optional[Path]:
        """Find the sessions.sqlite3 database file."""
        if self._db_path and self._db_path.exists():
            return self._db_path

        # Look for workspace subdirectory containing sessions.sqlite3
        if not self.sessions_dir.exists():
            logger.warning(f"Sessions directory not found: {self.sessions_dir}")
            return None

        for subdir in self.sessions_dir.iterdir():
            if subdir.is_dir():
                db_path = subdir / "sessions.sqlite3"
                if db_path.exists():
                    self._db_path = db_path
                    logger.info(f"Found sessions database: {db_path}")
                    return db_path

        logger.warning("No sessions.sqlite3 found in sessions directory")
        return None

    def get_session_messages(
        self,
        chat_id: str,
        limit: int = 50,
        after_position: int = -1
    ) -> list[dict]:
        """
        Get messages from a session by chat_id.

        Args:
            chat_id: The chat ID from WebSocket event (without 'websocket:' prefix)
            limit: Maximum number of messages to return
            after_position: Only get messages after this position (-1 for all recent)

        Returns:
            List of message dicts with 'role' and 'content' keys, ordered by position ASC
        """
        db_path = self._find_db()
        if not db_path:
            return []

        # Convert chat_id to session key format
        session_key = f"websocket:{chat_id}"

        try:
            conn = sqlite3.connect(str(db_path), timeout=5.0)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            # Get most recent messages (order DESC, then reverse)
            # If after_position specified, get messages after that position
            if after_position >= 0:
                cursor.execute("""
                    SELECT position, record FROM messages
                    WHERE session_key = ? AND position > ?
                    ORDER BY position ASC
                    LIMIT ?
                """, (session_key, after_position, limit))
            else:
                # Get most recent messages
                cursor.execute("""
                    SELECT position, record FROM (
                        SELECT position, record FROM messages
                        WHERE session_key = ?
                        ORDER BY position DESC
                        LIMIT ?
                    ) ORDER BY position ASC
                """, (session_key, limit))

            messages = []
            for row in cursor.fetchall():
                try:
                    record = json.loads(row['record'])
                    role = record.get('role', '')
                    content = record.get('content', '')

                    # Skip tool calls and tool results for compression
                    if role in ('user', 'assistant') and content:
                        messages.append({
                            'role': role,
                            'content': content,
                            'position': row['position']
                        })
                except json.JSONDecodeError:
                    continue

            conn.close()
            return messages

        except sqlite3.Error as e:
            logger.error(f"Database error: {e}")
            return []

    def get_message_count(self, chat_id: str) -> int:
        """Get the number of messages in a session."""
        db_path = self._find_db()
        if not db_path:
            return 0

        session_key = f"websocket:{chat_id}"

        try:
            conn = sqlite3.connect(str(db_path), timeout=5.0)
            cursor = conn.cursor()
            cursor.execute(
                "SELECT COUNT(*) FROM messages WHERE session_key = ?",
                (session_key,)
            )
            count = cursor.fetchone()[0]
            conn.close()
            return count
        except sqlite3.Error as e:
            logger.error(f"Database error: {e}")
            return 0

    def get_max_position(self, chat_id: str) -> int:
        """Get the maximum message position in a session."""
        db_path = self._find_db()
        if not db_path:
            return -1

        session_key = f"websocket:{chat_id}"

        try:
            conn = sqlite3.connect(str(db_path), timeout=5.0)
            cursor = conn.cursor()
            cursor.execute(
                "SELECT MAX(position) FROM messages WHERE session_key = ?",
                (session_key,)
            )
            result = cursor.fetchone()[0]
            conn.close()
            return result if result is not None else -1
        except sqlite3.Error as e:
            logger.error(f"Database error: {e}")
            return -1

    def list_sessions(self, limit: int = 10) -> list[dict]:
        """List recent sessions."""
        db_path = self._find_db()
        if not db_path:
            return []

        try:
            conn = sqlite3.connect(str(db_path), timeout=5.0)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            cursor.execute("""
                SELECT key, updated_at, title, preview
                FROM sessions
                WHERE key LIKE 'websocket:%'
                ORDER BY updated_at DESC
                LIMIT ?
            """, (limit,))

            sessions = []
            for row in cursor.fetchall():
                sessions.append({
                    'key': row['key'],
                    'chat_id': row['key'].replace('websocket:', ''),
                    'updated_at': row['updated_at'],
                    'title': row['title'],
                    'preview': row['preview']
                })

            conn.close()
            return sessions

        except sqlite3.Error as e:
            logger.error(f"Database error: {e}")
            return []
