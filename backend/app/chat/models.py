"""Chat domain event models — discriminated-union StreamEvent hierarchy (Phase 4.7).

Replaces the monolithic :class:`app.models.StreamEvent` class with five
concrete Pydantic event models plus a ``StreamEvent`` union alias. Each model
carries only its own fields and a ``type`` discriminator literal, enabling
Pydantic v2 native discriminated-union validation and mypy-strict narrowing.

Analog: :mod:`app.llm.errors` (``ProbeErrorCode`` + ``ProbeError`` pattern).
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field


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
