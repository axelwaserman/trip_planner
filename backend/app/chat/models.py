"""Chat domain event models — StreamEvent ABC hierarchy (Phase 5 D-15, D-16, REQ-p5-stream-event-abc).

Phase 5 replaces the Phase 4.7 ``Annotated[..., Field(discriminator="type")]``
union alias with a real :class:`StreamEvent` ABC base class. The five concrete
event subclasses (``ContentEvent``, ``ThinkingEvent``, ``ToolCallEvent``,
``ToolResultEvent``, ``ErrorEvent``) explicitly subclass it via multiple
inheritance with :class:`pydantic.BaseModel`, making ``isinstance(event,
StreamEvent)`` checks first-class instead of relying on union narrowing.

Phase 6 / Plan 06-05a renames the wire correlation field on every event
subclass to ``conversation_id`` (D-03 codebase-wide rename). The Phase 4.7
wire-format invariant — the renamed key stays declared on each subclass
(rather than hoisted into the ABC) — is preserved so Pydantic v2 keeps
emitting the field LAST per subclass. RESEARCH OQ-01's "hoist into the base"
guidance was empirically verified to break the wire format in Phase 4.7 and
that empirical lock carries through unchanged here.

``StreamEvent`` itself is a pure marker ABC (:class:`abc.ABC`, NOT
:class:`BaseModel`); it overrides
:meth:`__get_pydantic_core_schema__` so that ``TypeAdapter(StreamEvent)``
builds a discriminated union of the five subclasses on the fly. This preserves
the Phase 4.7 ``TypeAdapter`` round-trip behaviour without a separate type alias.

Also hosts the chat conversation and message DTOs previously in ``app.models``:
``ConversationCreateRequest``, ``SessionCreateError``, ``ChatRequest``,
``RetryRequest``, ``ChatConversationInfo``, ``ChatConversationsListResponse``,
``ChatHistoryMessage``, ``ChatConversationHistoryResponse``.

Analog: :mod:`app.llm.errors` (``ProbeErrorCode`` + ``ProbeError`` pattern).
"""

from __future__ import annotations

import operator
from abc import ABC
from enum import StrEnum
from functools import reduce
from typing import TYPE_CHECKING, Annotated, Any, Literal
from urllib.parse import urlparse

from pydantic import BaseModel, Field, field_validator

if TYPE_CHECKING:
    from pydantic import GetCoreSchemaHandler
    from pydantic_core import CoreSchema


class ErrorCode(StrEnum):
    """Wire-level error taxonomy for chat stream events.

    A single source of truth for the three error origins emitted by
    :meth:`app.chat.service.ChatService.chat_stream` and consumed by
    the frontend's error-routing logic.

    Per CLAUDE.md, the wire-level snake_case values are part of the contract:
    they are consumed by the frontend and must NOT be renamed. New error codes
    are appended; existing codes are immutable. The ``session_error`` value
    survives the Phase 6 / Plan 06-05a rename for this reason — it is a
    wire-level snake_case taxonomy code, not the user-facing concept.
    """

    session_error = "session_error"
    tool_error = "tool_error"
    stream_error = "stream_error"


class StreamEvent(ABC):  # noqa: B024 - intentional marker ABC; see docstring "Why a pure ABC"
    """Marker ABC base for all SSE stream events (Phase 5 D-15, D-16, REQ-p5-stream-event-abc).

    Replaces the Phase 4.7 ``Annotated[..., Field(discriminator="type")]``
    union alias with a real ABC class. The five concrete subclasses
    (:class:`ContentEvent`, :class:`ThinkingEvent`, :class:`ToolCallEvent`,
    :class:`ToolResultEvent`, :class:`ErrorEvent`) inherit from
    :class:`pydantic.BaseModel` AND this ABC via multiple inheritance, so
    ``isinstance(event, StreamEvent)`` checks work first-class.

    Why a pure ABC (not ``class StreamEvent(BaseModel, ABC)``):
        - The Phase 4.7 wire layout puts ``conversation_id`` LAST on every
          subclass (per Plan 06-05a's wire correlation field rename). Pydantic v2
          emits base fields BEFORE subclass fields, so declaring
          ``conversation_id`` on a ``BaseModel`` base class would shift the
          field to the second position and break wire byte-equivalence
          (verified empirically in Phase 4.7).
        - Keeping ``StreamEvent`` as a pure ABC + multi-inheriting subclasses
          on ``BaseModel`` preserves field order naturally — each subclass
          declares its own fields in the canonical
          ``type, …, conversation_id`` shape.
        - :meth:`__get_pydantic_core_schema__` overrides at the ABC level so
          ``TypeAdapter(StreamEvent)`` resolves to a discriminated union of
          all current subclasses, preserving the Phase 4.7 round-trip
          behaviour.

    Per CLAUDE.md / D-03 this is an :class:`abc.ABC`, NOT
    :class:`typing.Protocol` — same rule that governs :class:`LLMProvider`.
    """

    @classmethod
    def __get_pydantic_core_schema__(cls, source_type: Any, handler: GetCoreSchemaHandler) -> CoreSchema:
        """Return a discriminated-union schema over the five concrete subclasses.

        Called once per :class:`pydantic.TypeAdapter` construction. Walks the
        runtime ``__subclasses__`` set so newly-added event classes are picked
        up automatically (none are expected in Phase 5 — this is just defensive).
        """
        sub_types = list(cls.__subclasses__())
        if not sub_types:
            # No concrete subclasses yet — fall through to default Pydantic
            # behaviour (likely an `any_schema`); never the production path.
            return handler(source_type)
        union = reduce(operator.or_, sub_types)
        # mypy can't statically resolve a runtime ``__subclasses__`` walk to a
        # type, but Pydantic v2 happily accepts the dynamic union here — the
        # discriminated-union schema is generated at runtime per-TypeAdapter.
        annotated = Annotated[union, Field(discriminator="type")]  # type: ignore[valid-type]
        return handler.generate_schema(annotated)


class ContentEvent(BaseModel, StreamEvent):
    """A content chunk emitted during LLM text generation."""

    type: Literal["content"] = "content"
    chunk: str = ""
    conversation_id: str


class ThinkingEvent(BaseModel, StreamEvent):
    """A reasoning/thinking chunk emitted during extended-thinking mode."""

    type: Literal["thinking"] = "thinking"
    chunk: str = ""
    conversation_id: str


class ToolCallEvent(BaseModel, StreamEvent):
    """Emitted when the LLM dispatches a tool call (before execution)."""

    type: Literal["tool_call"] = "tool_call"
    tool_name: str
    tool_args: dict[str, Any]
    conversation_id: str


class ToolResultEvent(BaseModel, StreamEvent):
    """Emitted after a tool call completes with its result."""

    type: Literal["tool_result"] = "tool_result"
    tool_name: str
    tool_result: str
    elapsed_ms: int
    conversation_id: str


class ErrorEvent(BaseModel, StreamEvent):
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
    conversation_id: str


# ============================================================================
# Chat Conversation and Message DTOs (moved from app.models in Phase 4.9-01;
# renamed/split in Phase 6 / Plan 06-05a per D-03 + REQ-p5-session-create-request-split)
# ============================================================================


class ConversationTarget(BaseModel):
    """What to talk to (Pydantic SRP split — REQ-p5-session-create-request-split).

    The "target" half of the request body for ``POST /api/chat/conversation``:
    which provider/model the conversation is bound to. Credentials live on
    :class:`ProviderCredentials` so the SSRF + length validators are owned by
    a single class.
    """

    provider: str | None = Field(default=None, description="LLM provider (ollama, openai, anthropic)")
    model: str | None = Field(default=None, description="Model name for the provider")


class ProviderCredentials(BaseModel):
    """How to reach a provider — relocated ``SessionCreateRequest`` validators (REQ-p5-session-create-request-split).

    The "credentials" half of the request body for ``POST /api/chat/conversation``.
    Both validators below were lifted byte-equivalent from the deleted
    ``SessionCreateRequest`` so the existing security tests transfer with no
    behaviour change:

    - SSRF guard on ``base_url`` (allowlist localhost / 127.0.0.1 /
      host.docker.internal; http/https schemes only).
    - Length cap on ``api_key`` (≤ 256 chars after whitespace stripping;
      empty-after-strip normalises to ``None``).

    Per D-09, ``api_key`` lives only in conversation memory — never logged
    or persisted.
    """

    base_url: str | None = None
    api_key: str | None = None

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


class ConversationCreateRequest(BaseModel):
    """Request body for ``POST /api/chat/conversation`` (Phase 6 — REQ-p5-session-create-request-split).

    Splits the legacy flat ``SessionCreateRequest`` into a nested ``target`` +
    ``credentials`` shape so each Pydantic model owns one concern. FastAPI
    rejects the legacy flat shape with HTTP 422 — clients must migrate to the
    nested form (06-05b ships the frontend follow-on in the same atomic PR).
    """

    target: ConversationTarget = Field(default_factory=ConversationTarget)
    credentials: ProviderCredentials | None = None


# Import SessionCreateError from providers.models to avoid duplicating the
# ProbeErrorCode-referencing model here. ``SessionCreateError`` is exempt from
# the D-03 rename — the wire-level error envelope shape is part of the
# ``ProbeErrorCode`` taxonomy contract (CLAUDE.md "wire-level snake_case
# values are immutable").
from app.providers.models import SessionCreateError as SessionCreateError  # noqa: E402


class ChatRequest(BaseModel):
    """Request model for chat endpoint."""

    message: str = Field(..., min_length=1, description="User message to send to the agent")
    conversation_id: str = Field(..., description="Conversation ID for continuity")


class RetryRequest(BaseModel):
    """Request model for the retry endpoint.

    Mirrors the ``ChatRequest`` pattern but carries only a ``conversation_id``.
    The last tool invocation to replay is stored server-side in
    ``_metadata[conversation_id]["last_tool_invocation"]``; the client never
    needs to re-send tool args — it just identifies the conversation.
    """

    conversation_id: str = Field(
        ...,
        description="Conversation id whose last tool invocation should be replayed.",
    )


class ChatConversationInfo(BaseModel):
    """One conversation entry returned by GET /api/chat/conversations (D-22, D-27)."""

    conversation_id: str = Field(..., description="Server-generated UUID for this conversation.")
    provider: str = Field(..., description="Wire-level provider name (e.g., 'ollama').")
    model: str = Field(..., description="Per-provider model identifier.")
    created_at: str = Field(..., description="ISO 8601 UTC timestamp.")
    first_message_preview: str | None = Field(
        default=None,
        description="First HumanMessage content, truncated to 80 chars; None if conversation has no messages yet.",
    )


class ChatConversationsListResponse(BaseModel):
    """Response shape for GET /api/chat/conversations (D-22, D-27)."""

    conversations: list[ChatConversationInfo] = Field(
        ..., description="Conversations owned by the authenticated user."
    )


class ChatHistoryMessage(BaseModel):
    """One message in a conversation's chat history.

    Used by GET /api/chat/conversations/{id} so the frontend can re-render a
    previously-active conversation when the user clicks it in the Sidebar. Only
    user/assistant turns are surfaced — tool execution traces and reasoning
    chunks are stream-only artefacts that don't round-trip cleanly.
    """

    role: Literal["user", "assistant"] = Field(..., description="Message author.")
    content: str = Field(..., description="Message text (Markdown allowed for assistant).")


class ChatConversationHistoryResponse(BaseModel):
    """Response shape for GET /api/chat/conversations/{conversation_id}.

    Returned only when the authenticated user owns the requested conversation.
    Non-owners and missing conversations both surface as 404 to avoid leaking
    conversation existence (mirrors the per-user-partition pattern from
    GET /api/chat/conversations and DELETE /api/chat/conversation/{id}).
    """

    conversation_id: str = Field(..., description="Echoed conversation UUID.")
    provider: str = Field(..., description="Provider the conversation is bound to.")
    model: str = Field(..., description="Model the conversation is bound to.")
    messages: list[ChatHistoryMessage] = Field(
        default_factory=list,
        description="User/assistant turns in chronological order.",
    )
