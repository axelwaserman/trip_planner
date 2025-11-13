"""Chat session domain models."""

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field


class ChatSession(BaseModel):
    """Domain model for a chat session.

    Each session represents an independent conversation with:
    - Unique identifier for isolation across tabs/users
    - Timestamps for TTL cleanup
    - Metadata for storing user preferences (LLM provider, model, etc.)
    - Message count for analytics
    """

    session_id: str = Field(..., description="Unique session identifier (UUID)")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="UTC timestamp when session was created",
    )
    last_activity: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="UTC timestamp of last message in this session",
    )
    message_count: int = Field(
        default=0, ge=0, description="Total number of messages in this session"
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Session-scoped metadata (e.g., llm_provider, llm_model, user_prefs)",
    )

    def touch(self) -> None:
        """Update last_activity to current time.

        Call this after each message to keep session alive.
        """
        self.last_activity = datetime.now(UTC)

    def increment_message_count(self) -> None:
        """Increment message count (called after each user/assistant message pair)."""
        self.message_count += 1

    def is_expired(self, max_age_seconds: int) -> bool:
        """Check if session has expired based on inactivity.

        Args:
            max_age_seconds: Maximum age in seconds since last activity

        Returns:
            True if session should be cleaned up
        """
        age = (datetime.now(UTC) - self.last_activity).total_seconds()
        return age > max_age_seconds
