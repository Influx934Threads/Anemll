"""
Nanobot API Client - Interacts with nanobot's REST API.

Used to query session state and potentially inject context.
"""

import asyncio
import json
import logging
from typing import Any, Optional

import aiohttp

logger = logging.getLogger(__name__)


class NanobotClient:
    """
    Client for nanobot's REST API.

    Provides methods to interact with nanobot for:
    - Querying session state
    - Getting session history
    - Health checks
    """

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:8900",
        api_key: str = "",
        timeout: float = 30.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = aiohttp.ClientTimeout(total=timeout)
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create HTTP session."""
        if self._session is None or self._session.closed:
            headers = {}
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"
            self._session = aiohttp.ClientSession(
                timeout=self.timeout,
                headers=headers,
            )
        return self._session

    async def close(self):
        """Close the HTTP session."""
        if self._session and not self._session.closed:
            await self._session.close()

    async def health_check(self) -> bool:
        """Check if nanobot API is healthy."""
        try:
            session = await self._get_session()
            async with session.get(f"{self.base_url}/health") as resp:
                return resp.status == 200
        except Exception as e:
            logger.debug(f"Health check failed: {e}")
            return False

    async def get_sessions(self) -> list[dict]:
        """Get list of active sessions."""
        try:
            session = await self._get_session()
            async with session.get(f"{self.base_url}/api/sessions") as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data.get("sessions", [])
                logger.warning(f"Failed to get sessions: {resp.status}")
                return []
        except Exception as e:
            logger.error(f"Error getting sessions: {e}")
            return []

    async def get_session_info(self, session_key: str) -> Optional[dict]:
        """Get information about a specific session."""
        try:
            session = await self._get_session()
            async with session.get(
                f"{self.base_url}/api/sessions/{session_key}"
            ) as resp:
                if resp.status == 200:
                    return await resp.json()
                logger.debug(f"Session not found: {session_key}")
                return None
        except Exception as e:
            logger.error(f"Error getting session info: {e}")
            return None

    async def get_session_messages(
        self,
        session_key: str,
        limit: int = 100
    ) -> list[dict]:
        """Get messages from a session."""
        try:
            session = await self._get_session()
            params = {"limit": limit}
            async with session.get(
                f"{self.base_url}/api/sessions/{session_key}/messages",
                params=params,
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data.get("messages", [])
                return []
        except Exception as e:
            logger.error(f"Error getting messages: {e}")
            return []

    async def send_system_message(
        self,
        session_key: str,
        content: str,
        metadata: Optional[dict] = None,
    ) -> bool:
        """
        Send a system-level message to a session.

        This can be used to inject context summaries.
        """
        try:
            session = await self._get_session()
            payload = {
                "session_key": session_key,
                "content": content,
                "role": "system",
                "metadata": metadata or {},
            }
            async with session.post(
                f"{self.base_url}/api/sessions/{session_key}/inject",
                json=payload,
            ) as resp:
                if resp.status in (200, 201):
                    logger.debug(f"Injected context to {session_key}")
                    return True
                logger.warning(f"Failed to inject context: {resp.status}")
                return False
        except Exception as e:
            logger.error(f"Error injecting context: {e}")
            return False

    async def get_stats(self) -> dict:
        """Get nanobot statistics."""
        try:
            session = await self._get_session()
            async with session.get(f"{self.base_url}/api/stats") as resp:
                if resp.status == 200:
                    return await resp.json()
                return {}
        except Exception as e:
            logger.error(f"Error getting stats: {e}")
            return {}


class NanobotWSClient:
    """
    WebSocket client for nanobot.

    Connects to nanobot's WebSocket for real-time message monitoring.
    """

    def __init__(
        self,
        ws_url: str = "ws://127.0.0.1:8765",
        token: str = "",
    ):
        self.ws_url = ws_url
        self.token = token
        self._ws = None
        self._connected = False

    @property
    def connected(self) -> bool:
        return self._connected and self._ws is not None

    async def connect(self) -> bool:
        """Connect to nanobot WebSocket."""
        import websockets

        try:
            url = self.ws_url
            if self.token:
                url = f"{url}?token={self.token}"

            self._ws = await websockets.connect(url)
            self._connected = True
            logger.info(f"Connected to nanobot WebSocket at {self.ws_url}")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to WebSocket: {e}")
            self._connected = False
            return False

    async def disconnect(self):
        """Disconnect from WebSocket."""
        if self._ws:
            await self._ws.close()
            self._ws = None
        self._connected = False

    async def receive(self) -> Optional[str]:
        """Receive a message from WebSocket."""
        if not self._ws:
            return None
        try:
            return await self._ws.recv()
        except Exception as e:
            logger.error(f"WebSocket receive error: {e}")
            self._connected = False
            return None

    async def send(self, message: dict) -> bool:
        """Send a message to WebSocket."""
        if not self._ws:
            return False
        try:
            await self._ws.send(json.dumps(message))
            return True
        except Exception as e:
            logger.error(f"WebSocket send error: {e}")
            return False

    async def iter_messages(self):
        """Async iterator over WebSocket messages."""
        while self._connected and self._ws:
            msg = await self.receive()
            if msg is None:
                break
            yield msg


# ─── ANE Context Client ───

DEFAULT_ANE_CONTEXT_URL = "http://127.0.0.1:8766"


class ANEContextClient:
    """
    Client for fetching compressed context from ANE daemon.

    This is used by nanobot to inject compressed history before inference.

    Usage:
        client = ANEContextClient()
        context = await client.get_context_text(session_key)
    """

    def __init__(
        self,
        base_url: str = DEFAULT_ANE_CONTEXT_URL,
        timeout: float = 5.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create HTTP session."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=self.timeout)
            )
        return self._session

    async def close(self):
        """Close the HTTP session."""
        if self._session and not self._session.closed:
            await self._session.close()

    async def get_context(self, session_key: str) -> Optional[dict]:
        """
        Get compressed context for a session.

        Args:
            session_key: The session ID to get context for

        Returns:
            Dict with 'context' and 'stats' keys, or None if not available
        """
        try:
            session = await self._get_session()
            url = f"{self.base_url}/context/{session_key}"

            async with session.get(url) as response:
                if response.status != 200:
                    logger.debug(f"Context request failed: {response.status}")
                    return None

                data = await response.json()
                context = data.get("context", "")

                if not context:
                    return None

                return {
                    "session_key": session_key,
                    "context": context,
                    "stats": data.get("stats", {}),
                }

        except aiohttp.ClientError as e:
            logger.debug(f"Failed to fetch context: {e}")
            return None
        except asyncio.TimeoutError:
            logger.debug("Context request timed out")
            return None

    async def get_context_text(self, session_key: str) -> str:
        """
        Get just the context text for a session.

        Convenience method that returns empty string if not available.
        """
        response = await self.get_context(session_key)
        return response["context"] if response else ""

    async def is_available(self) -> bool:
        """Check if the ANE daemon context server is available."""
        try:
            session = await self._get_session()
            url = f"{self.base_url}/status"

            async with session.get(url) as response:
                return response.status == 200

        except Exception:
            return False

    async def get_metrics(self) -> Optional[dict]:
        """Get compression metrics from the daemon."""
        try:
            session = await self._get_session()
            url = f"{self.base_url}/metrics"

            async with session.get(url) as response:
                if response.status == 200:
                    return await response.json()
                return None

        except Exception:
            return None


# Convenience function for getting context
async def get_ane_context(session_key: str, base_url: str = DEFAULT_ANE_CONTEXT_URL) -> str:
    """
    Convenience function to get ANE compressed context for a session.

    Usage:
        from nanobot_ane.nanobot_client import get_ane_context

        context = await get_ane_context("my-session-id")
    """
    client = ANEContextClient(base_url=base_url)
    try:
        return await client.get_context_text(session_key)
    finally:
        await client.close()
