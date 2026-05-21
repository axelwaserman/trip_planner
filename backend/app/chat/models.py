"""Chat domain event models — discriminated-union StreamEvent hierarchy (Phase 4.7).

Replaces the monolithic :class:`app.models.StreamEvent` class with five
concrete Pydantic event models plus a ``StreamEvent`` union alias. Each model
carries only its own fields and a ``type`` discriminator literal, enabling
Pydantic v2 native discriminated-union validation and mypy-strict narrowing.

Also hosts the chat session and message DTOs previously in ``app.models``:
``SessionCreateRequest``, ``SessionCreateError``, ``ChatRequest``,
``RetryRequest``, ``ChatSessionInfo``, ``ChatSessionsListResponse``,
``ChatHistoryMessage``, ``ChatSessionHistoryResponse``.

Analog: :mod:`app.llm.errors` (``ProbeErrorCode`` + ``ProbeError`` pattern).
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Any, Literal
from urllib.parse import urlparse

from pydantic import BaseModel, Field, field_validator


class ErrorCode(StrEnum):
    """Wire-level error taxonomy for chat stream events.

    A single source of truth for the three error origins emitted by
    :meth:`app.chat.service.ChatService.chat_stream` and consumed by
    the frontend's error-routing logic.

    Per CLAUDE.md, the wire-level snake_case values are part of the contract:
    they are consumed by the frontend and must NOT be renamed. New error codes
    are appended; existing codes are immutable.
    """

    session_error = "session_error"
    tool_error = "tool_error"
    stream_error = "stream_error"


class ContentEvent(BaseModel):
    """A content chunk emitted during LLM text generation."""

    type: Literal["content"] = "content"
    chunk: str = ""
    session_id: str


class ThinkingEvent(BaseModel):
    """A reasoning/thinking chunk emitted during extended-thinking mode."""

    type: Literal["thinking"] = "thinking"
    chunk: str = ""
    session_id: str


class ToolCallEvent(BaseModel):
    """Emitted when the LLM dispatches a tool call (before execution)."""

    type: Literal["tool_call"] = "tool_call"
    tool_name: str
    tool_args: dict[str, Any]
    session_id: str


class ToolResultEvent(BaseModel):
    """Emitted after a tool call completes with its result."""

    type: Literal["tool_result"] = "tool_result"
    tool_name: str
    tool_result: str
    elapsed_ms: int
    session_id: str


class ErrorEvent(BaseModel):
    """Emitted when a tool execution or stream-level error occurs.

    ``retryable`` drives whether the frontend shows a retry control inline
    on the ``ToolExecutionCard``. ``tool_name`` identifies which tool errored.
    ``raw_detail`` carries the scrubbed exception string
    (always passed through :func:`app.llm.log_scrubbing._scrub` at every
    construction site in :mod:`app.chat.service`) — the frontend decides
    whether to render it (e.g. in a collapsible debug section).
    """

    type: Literal["error"] = "error"
    error_code: ErrorCode
    message: str
    retryable: bool
    tool_name: str | None = None
    raw_detail: str | None = None
    session_id: str


# DO NOT instantiate StreamEvent directly; it is a Field-discriminated union alias
# used only for type annotations and TypeAdapter validation.
StreamEvent = Annotated[
    ContentEvent | ThinkingEvent | ToolCallEvent | ToolResultEvent | ErrorEvent,
    Field(discriminator="type"),
]


# ============================================================================
# Chat Session and Message DTOs (moved from app.models in Phase 4.9-01)
# ============================================================================


class SessionCreateRequest(BaseModel):
    """Request model for creating a new chat session.

    Per CONTEXT.md D-24, the canonical session-create payload carries four
    optional fields: provider, model, base_url (local providers only), api_key
    (cloud providers only). Per D-09, ``api_key`` lives only in session memory —
    never logged or persisted.

    Validators enforce the threat-model mitigations from PLAN.md:
    - SSRF guard on ``base_url`` (allowlist localhost / 127.0.0.1 /
      host.docker.internal; http/https schemes only).
    - Length cap on ``api_key`` (≤ 256 chars after whitespace stripping;
      empty-after-strip normalises to ``None``).
    """

    provider: str | None = Field(default=None, description="LLM provider (ollama, openai, anthropic)")
    model: str | None = Field(default=None, description="Model name for the provider")
    base_url: str | None = Field(
        default=None,
        description="Local providers only; ignored for cloud",
    )
    api_key: str | None = Field(
        default=None,
        description=(
            "Cloud providers only; ignored for local. Stored in session memory only — never logged or persisted."
        ),
    )

    @field_validator("api_key")
    @classmethod
    def _strip_and_bound_api_key(cls, v: str | None) -> str | None:
        """Strip whitespace, normalise empty to None, cap length at 256 chars."""
        if v is None:
            return None
        stripped = v.strip()
        if not stripped:
            return None
        if len(stripped) > 256:
            raise ValueError("api_key exceeds maximum length (256 chars)")
        return stripped

    @field_validator("base_url")
    @classmethod
    def _validate_base_url(cls, v: str | None) -> str | None:
        """SSRF guard: allowlist of {localhost, 127.0.0.1, host.docker.internal}; http/https only."""
        if v is None:
            return None
        parsed = urlparse(v)
        if parsed.scheme not in {"http", "https"}:
            raise ValueError("base_url must be http or https")
        if parsed.hostname not in {"localhost", "127.0.0.1", "host.docker.internal"}:
            raise ValueError("base_url host must be localhost, 127.0.0.1, or host.docker.internal in v1")
        return v


# Import SessionCreateError from providers.models to avoid duplicating the
# ProbeErrorCode-referencing model here.
from app.providers.models import SessionCreateError as SessionCreateError  # noqa: E402


class ChatRequest(BaseModel):
    """Request model for chat endpoint."""

    message: str = Field(..., min_length=1, description="User message to send to the agent")
    session_id: str = Field(..., description="Session ID for conversation continuity")


class RetryRequest(BaseModel):
    """Request model for the retry endpoint.

    Mirrors the ``ChatRequest`` pattern but carries only a ``session_id``.
    The last tool invocation to replay is stored server-side in
    ``_metadata[session_id]["last_tool_invocation"]``; the client never
    needs to re-send tool args — it just identifies the session.
    """

    session_id: str = Field(
        ...,
        description="Session id whose last tool invocation should be replayed.",
    )


class ChatSessionInfo(BaseModel):
    """One session entry returned by GET /api/chat/sessions (D-22, D-27)."""

    session_id: str = Field(..., description="Server-generated UUID for this session.")
    provider: str = Field(..., description="Wire-level provider name (e.g., 'ollama').")
    model: str = Field(..., description="Per-provider model identifier.")
    created_at: str = Field(..., description="ISO 8601 UTC timestamp.")
    first_message_preview: str | None = Field(
        default=None,
        description="First HumanMessage content, truncated to 80 chars; None if session has no messages yet.",
    )


class ChatSessionsListResponse(BaseModel):
    """Response shape for GET /api/chat/sessions (D-22, D-27)."""

    sessions: list[ChatSessionInfo] = Field(..., description="Sessions owned by the authenticated user.")


class ChatHistoryMessage(BaseModel):
    """One message in a session's chat history.

    Used by GET /api/chat/sessions/{id} so the frontend can re-render a
    previously-active session when the user clicks it in the Sidebar. Only
    user/assistant turns are surfaced — tool execution traces and reasoning
    chunks are stream-only artefacts that don't round-trip cleanly.
    """

    role: Literal["user", "assistant"] = Field(..., description="Message author.")
    content: str = Field(..., description="Message text (Markdown allowed for assistant).")


class ChatSessionHistoryResponse(BaseModel):
    """Response shape for GET /api/chat/sessions/{session_id}.

    Returned only when the authenticated user owns the requested session.
    Non-owners and missing sessions both surface as 404 to avoid leaking
    session existence (mirrors the per-user-partition pattern from
    GET /api/chat/sessions and DELETE /api/chat/session/{id}).
    """

    session_id: str = Field(..., description="Echoed session UUID.")
    provider: str = Field(..., description="Provider the session is bound to.")
    model: str = Field(..., description="Model the session is bound to.")
    messages: list[ChatHistoryMessage] = Field(
        default_factory=list,
        description="User/assistant turns in chronological order.",
    )
