"""
Session Database Reader - Reads nanobot session data from SQLite database.

Provides direct access to nanobot's session storage for reading
conversation messages.

Nanobot stores sessions in SQLite at:
  ~/.nanobot/sessions/<workspace_hash>/sessions.sqlite3
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
        self._workspace_dir: Optional[Path] = None
        self._db_path: Optional[Path] = None

    def _find_workspace_dir(self) -> Optional[Path]:
        """Find the workspace subdirectory containing sessions.sqlite3."""
        if self._workspace_dir and self._workspace_dir.exists():
            return self._workspace_dir

        if not self.sessions_dir.exists():
            logger.warning(f"Sessions directory not found: {self.sessions_dir}")
            return None

        # Find workspace subdirectory (hash-named folder with sessions.sqlite3)
        for subdir in self.sessions_dir.iterdir():
            if subdir.is_dir() and not subdir.name.startswith('.'):
                db_path = subdir / "sessions.sqlite3"
                if db_path.exists():
                    self._workspace_dir = subdir
                    self._db_path = db_path
                    logger.info(f"Found sessions database: {db_path}")
                    return subdir

        logger.warning("No workspace with sessions.sqlite3 found")
        return None

    def _get_db_path(self) -> Optional[Path]:
        """Get path to sessions.sqlite3."""
        if self._db_path and self._db_path.exists():
            return self._db_path
        self._find_workspace_dir()
        return self._db_path

    def _connect(self) -> Optional[sqlite3.Connection]:
        """Create a database connection."""
        db_path = self._get_db_path()
        if not db_path:
            return None
        try:
            conn = sqlite3.connect(str(db_path), timeout=5.0)
            conn.row_factory = sqlite3.Row
            return conn
        except Exception as e:
            logger.error(f"Failed to connect to database: {e}")
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
            chat_id: The chat ID (without 'websocket:' prefix)
            limit: Maximum number of messages to return
            after_position: Only get messages after this position (-1 for all recent)

        Returns:
            List of message dicts with 'role', 'content', and 'position' keys
        """
        conn = self._connect()
        if not conn:
            return []

        session_key = f"websocket:{chat_id}"
        messages = []

        try:
            cursor = conn.cursor()

            # Build query
            if after_position >= 0:
                query = """
                    SELECT position, record FROM messages
                    WHERE session_key = ? AND position > ?
                    ORDER BY position ASC
                """
                params = (session_key, after_position)
            else:
                query = """
                    SELECT position, record FROM messages
                    WHERE session_key = ?
                    ORDER BY position DESC
                    LIMIT ?
                """
                params = (session_key, limit if limit > 0 else 1000)

            cursor.execute(query, params)
            rows = cursor.fetchall()

            # If we got DESC order, reverse to ASC
            if after_position < 0:
                rows = list(reversed(rows))

            for row in rows:
                try:
                    record = json.loads(row['record'])
                    role = record.get('role', '')
                    content = record.get('content', '')

                    # Only include user/assistant messages with content
                    if role in ('user', 'assistant') and content:
                        messages.append({
                            'role': role,
                            'content': content,
                            'position': row['position']
                        })
                except json.JSONDecodeError:
                    continue

            # Apply limit if we're filtering by position
            if after_position >= 0 and limit > 0 and len(messages) > limit:
                messages = messages[-limit:]

        except Exception as e:
            logger.error(f"Error querying messages: {e}")
        finally:
            conn.close()

        return messages

    def get_message_count(self, chat_id: str) -> int:
        """Get the number of user/assistant messages in a session."""
        conn = self._connect()
        if not conn:
            return 0

        session_key = f"websocket:{chat_id}"
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT COUNT(*) FROM messages WHERE session_key = ?",
                (session_key,)
            )
            return cursor.fetchone()[0]
        except Exception as e:
            logger.error(f"Error counting messages: {e}")
            return 0
        finally:
            conn.close()

    def get_max_position(self, chat_id: str) -> int:
        """Get the maximum message position in a session."""
        conn = self._connect()
        if not conn:
            return -1

        session_key = f"websocket:{chat_id}"
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT MAX(position) FROM messages WHERE session_key = ?",
                (session_key,)
            )
            result = cursor.fetchone()[0]
            return result if result is not None else -1
        except Exception as e:
            logger.error(f"Error getting max position: {e}")
            return -1
        finally:
            conn.close()

    def list_sessions(self, limit: int = 10) -> list[dict]:
        """List recent sessions."""
        conn = self._connect()
        if not conn:
            return []

        sessions = []
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT s.key, s.created_at, s.updated_at,
                       (SELECT COUNT(*) FROM messages m WHERE m.session_key = s.key) as msg_count
                FROM sessions s
                WHERE s.key LIKE 'websocket:%'
                ORDER BY s.updated_at DESC
                LIMIT ?
            """, (limit,))

            for row in cursor.fetchall():
                session_key = row['key']
                chat_id = session_key.replace('websocket:', '') if session_key.startswith('websocket:') else session_key
                sessions.append({
                    'key': session_key,
                    'chat_id': chat_id,
                    'created_at': row['created_at'],
                    'updated_at': row['updated_at'],
                    'msg_count': row['msg_count']
                })
        except Exception as e:
            logger.error(f"Error listing sessions: {e}")
        finally:
            conn.close()

        return sessions

    def get_active_sessions_with_positions(self, limit: int = 20) -> list[dict]:
        """
        Get active sessions with their max message positions.

        Returns sessions ordered by most recent message activity.
        """
        conn = self._connect()
        if not conn:
            return []

        sessions = []
        try:
            cursor = conn.cursor()
            # Get sessions with their max positions, ordered by max position (most recent activity)
            cursor.execute("""
                SELECT
                    m.session_key,
                    MAX(m.position) as max_pos,
                    COUNT(*) as msg_count
                FROM messages m
                WHERE m.session_key LIKE 'websocket:%'
                GROUP BY m.session_key
                ORDER BY max_pos DESC
                LIMIT ?
            """, (limit,))

            for row in cursor.fetchall():
                session_key = row['session_key']
                chat_id = session_key.replace('websocket:', '') if session_key.startswith('websocket:') else session_key
                sessions.append({
                    'session_key': session_key,
                    'chat_id': chat_id,
                    'max_pos': row['max_pos'],
                    'msg_count': row['msg_count']
                })
        except Exception as e:
            logger.error(f"Error getting active sessions: {e}")
        finally:
            conn.close()

        return sessions
