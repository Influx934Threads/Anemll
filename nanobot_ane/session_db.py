"""
Session Database Reader - Reads nanobot session data from JSONL files.

Provides direct access to nanobot's session storage for reading
conversation messages.

Nanobot stores sessions as JSONL files in:
  ~/.nanobot/sessions/<workspace_hash>/<base64_session_key>.jsonl
"""

import base64
import json
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Default nanobot sessions directory
DEFAULT_SESSIONS_DIR = "~/.nanobot/sessions"


class SessionDBReader:
    """
    Reads session data directly from nanobot's JSONL files.
    """

    def __init__(self, sessions_dir: str = DEFAULT_SESSIONS_DIR):
        self.sessions_dir = Path(sessions_dir).expanduser()
        self._workspace_dir: Optional[Path] = None

    def _find_workspace_dir(self) -> Optional[Path]:
        """Find the workspace subdirectory containing session files."""
        if self._workspace_dir and self._workspace_dir.exists():
            return self._workspace_dir

        if not self.sessions_dir.exists():
            logger.warning(f"Sessions directory not found: {self.sessions_dir}")
            return None

        # Find workspace subdirectory (hash-named folder)
        for subdir in self.sessions_dir.iterdir():
            if subdir.is_dir() and not subdir.name.startswith('.'):
                # Check if it has JSONL files
                jsonl_files = list(subdir.glob("*.jsonl"))
                if jsonl_files:
                    self._workspace_dir = subdir
                    logger.info(f"Found sessions workspace: {subdir}")
                    return subdir

        logger.warning("No workspace with session files found")
        return None

    def _session_key_to_filename(self, chat_id: str) -> str:
        """Convert chat_id to base64-encoded filename."""
        session_key = f"websocket:{chat_id}"
        # Use standard base64 encoding, strip padding (nanobot uses this format)
        encoded = base64.b64encode(session_key.encode()).decode().rstrip('=')
        return f"{encoded}.jsonl"

    def _filename_to_chat_id(self, filename: str) -> Optional[str]:
        """Convert base64-encoded filename back to chat_id."""
        try:
            # Remove .jsonl extension
            encoded = filename.replace('.jsonl', '')
            # Add padding if needed (base64 strings must be multiple of 4)
            padding = 4 - len(encoded) % 4
            if padding != 4:
                encoded += '=' * padding
            # Decode base64
            decoded = base64.b64decode(encoded).decode()
            # Extract chat_id from "websocket:<chat_id>"
            if decoded.startswith('websocket:'):
                return decoded[10:]  # len('websocket:') = 10
            return None
        except Exception:
            return None

    def _get_session_file(self, chat_id: str) -> Optional[Path]:
        """Get the JSONL file path for a session."""
        workspace_dir = self._find_workspace_dir()
        if not workspace_dir:
            return None

        filename = self._session_key_to_filename(chat_id)
        file_path = workspace_dir / filename

        if file_path.exists():
            return file_path

        logger.debug(f"Session file not found: {file_path}")
        return None

    def _parse_jsonl_file(self, file_path: Path) -> list[dict]:
        """Parse a JSONL file and return all records."""
        records = []
        try:
            with open(file_path, 'r') as f:
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        record = json.loads(line)
                        record['_line_num'] = line_num  # Track position
                        records.append(record)
                    except json.JSONDecodeError as e:
                        logger.warning(f"Invalid JSON at line {line_num}: {e}")
                        continue
        except Exception as e:
            logger.error(f"Error reading {file_path}: {e}")
        return records

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
            after_position: Only get messages after this line number (-1 for all recent)

        Returns:
            List of message dicts with 'role', 'content', and 'position' keys
        """
        file_path = self._get_session_file(chat_id)
        if not file_path:
            return []

        records = self._parse_jsonl_file(file_path)

        messages = []
        for record in records:
            # Skip metadata
            if record.get('_type') == 'metadata':
                continue

            role = record.get('role', '')
            content = record.get('content', '')
            position = record.get('_line_num', 0)

            # Skip tool calls and tool results for compression
            if role in ('user', 'assistant') and content:
                # Apply position filter
                if after_position >= 0 and position <= after_position:
                    continue

                messages.append({
                    'role': role,
                    'content': content,
                    'position': position
                })

        # Return most recent messages up to limit
        if limit > 0 and len(messages) > limit:
            messages = messages[-limit:]

        return messages

    def get_message_count(self, chat_id: str) -> int:
        """Get the number of user/assistant messages in a session."""
        messages = self.get_session_messages(chat_id, limit=0)  # No limit
        return len(messages)

    def get_max_position(self, chat_id: str) -> int:
        """Get the maximum message position (line number) in a session."""
        file_path = self._get_session_file(chat_id)
        if not file_path:
            return -1

        try:
            with open(file_path, 'r') as f:
                line_count = sum(1 for line in f if line.strip())
            return line_count
        except Exception as e:
            logger.error(f"Error counting lines in {file_path}: {e}")
            return -1

    def list_sessions(self, limit: int = 10) -> list[dict]:
        """List recent sessions."""
        workspace_dir = self._find_workspace_dir()
        if not workspace_dir:
            return []

        sessions = []
        for jsonl_file in sorted(
            workspace_dir.glob("*.jsonl"),
            key=lambda f: f.stat().st_mtime,
            reverse=True
        ):
            chat_id = self._filename_to_chat_id(jsonl_file.name)
            if not chat_id:
                continue

            # Get metadata from first line
            try:
                with open(jsonl_file, 'r') as f:
                    first_line = f.readline()
                    if first_line:
                        metadata = json.loads(first_line)
                        if metadata.get('_type') == 'metadata':
                            sessions.append({
                                'key': f"websocket:{chat_id}",
                                'chat_id': chat_id,
                                'updated_at': metadata.get('updated_at', ''),
                                'title': metadata.get('metadata', {}).get('title', ''),
                                'file_path': str(jsonl_file)
                            })
            except Exception:
                continue

            if len(sessions) >= limit:
                break

        return sessions

    def get_active_sessions_with_positions(self, limit: int = 20) -> list[dict]:
        """
        Get active sessions with their max message positions.

        Returns sessions ordered by most recent modification time.
        """
        workspace_dir = self._find_workspace_dir()
        if not workspace_dir:
            return []

        sessions = []
        for jsonl_file in sorted(
            workspace_dir.glob("*.jsonl"),
            key=lambda f: f.stat().st_mtime,
            reverse=True
        ):
            # Only include websocket sessions
            chat_id = self._filename_to_chat_id(jsonl_file.name)
            if not chat_id:
                continue

            # Count lines (positions)
            try:
                with open(jsonl_file, 'r') as f:
                    line_count = sum(1 for line in f if line.strip())

                sessions.append({
                    'session_key': f"websocket:{chat_id}",
                    'chat_id': chat_id,
                    'max_pos': line_count,
                    'msg_count': line_count,  # Approximate
                    'file_path': str(jsonl_file),
                    'mtime': jsonl_file.stat().st_mtime
                })
            except Exception as e:
                logger.warning(f"Error reading {jsonl_file}: {e}")
                continue

            if len(sessions) >= limit:
                break

        return sessions
