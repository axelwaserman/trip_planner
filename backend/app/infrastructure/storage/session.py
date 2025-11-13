"""Session storage abstraction and implementations."""

import uuid
from abc import ABC, abstractmethod
from typing import Any

from langchain_core.chat_history import InMemoryChatMessageHistory

from app.domain.session import ChatSession


class SessionStore(ABC):
    """Abstract base class for session storage backends.

    Implementations can be in-memory (development), Redis (production),
    or database-backed (persistent storage).
    """

    @abstractmethod
    async def create_session(self, metadata: dict[str, Any] | None = None) -> ChatSession:
        """Create a new chat session with unique ID.

        Args:
            metadata: Optional metadata dict for the session (e.g., provider info)

        Returns:
            Newly created ChatSession with generated session_id
        """
        ...

    @abstractmethod
    async def get_session(self, session_id: str) -> ChatSession | None:
        """Retrieve a session by ID.

        Args:
            session_id: Unique session identifier

        Returns:
            ChatSession if found, None if not found or expired
        """
        ...

    @abstractmethod
    async def update_session(self, session: ChatSession) -> None:
        """Update an existing session (e.g., after activity).

        Args:
            session: Session to update with new state
        """
        ...

    @abstractmethod
    async def delete_session(self, session_id: str) -> bool:
        """Delete a session and its history.

        Args:
            session_id: Session to delete

        Returns:
            True if session existed and was deleted, False otherwise
        """
        ...

    @abstractmethod
    async def get_history(self, session_id: str) -> InMemoryChatMessageHistory:
        """Get conversation history for a session.

        Args:
            session_id: Session identifier

        Returns:
            Chat message history (creates empty if not exists)
        """
        ...

    @abstractmethod
    async def cleanup_expired(self, max_age_seconds: int) -> int:
        """Remove expired sessions based on inactivity.

        Args:
            max_age_seconds: Maximum age since last activity

        Returns:
            Number of sessions cleaned up
        """
        ...


class InMemorySessionStore(SessionStore):
    """In-memory session storage with TTL cleanup.

    Suitable for development and single-server deployments.
    For production multi-server setup, use Redis-backed store.
    """

    def __init__(self, default_ttl_seconds: int = 3600) -> None:
        """Initialize in-memory store.

        Args:
            default_ttl_seconds: Default session TTL (1 hour)
        """
        self._sessions: dict[str, ChatSession] = {}
        self._histories: dict[str, InMemoryChatMessageHistory] = {}
        self._default_ttl = default_ttl_seconds

    async def create_session(self, metadata: dict[str, Any] | None = None) -> ChatSession:
        """Create a new session with generated UUID.

        Args:
            metadata: Optional metadata dict for the session

        Returns:
            Newly created ChatSession
        """
        session = ChatSession(
            session_id=str(uuid.uuid4()),
            metadata=metadata or {},
        )
        self._sessions[session.session_id] = session
        self._histories[session.session_id] = InMemoryChatMessageHistory()
        return session

    async def get_session(self, session_id: str) -> ChatSession | None:
        """Retrieve session, cleaning up expired sessions first."""
        await self.cleanup_expired(self._default_ttl)
        return self._sessions.get(session_id)

    async def update_session(self, session: ChatSession) -> None:
        """Update session in store."""
        if session.session_id in self._sessions:
            self._sessions[session.session_id] = session

    async def delete_session(self, session_id: str) -> bool:
        """Delete session and history."""
        session_existed = session_id in self._sessions
        self._sessions.pop(session_id, None)
        self._histories.pop(session_id, None)
        return session_existed

    async def get_history(self, session_id: str) -> InMemoryChatMessageHistory:
        """Get or create history for session."""
        if session_id not in self._histories:
            self._histories[session_id] = InMemoryChatMessageHistory()
        return self._histories[session_id]

    async def cleanup_expired(self, max_age_seconds: int) -> int:
        """Remove expired sessions based on last_activity."""
        expired_ids = [
            sid for sid, session in self._sessions.items() if session.is_expired(max_age_seconds)
        ]

        for session_id in expired_ids:
            await self.delete_session(session_id)

        return len(expired_ids)

    def get_session_count(self) -> int:
        """Get current number of active sessions (for monitoring)."""
        return len(self._sessions)
