"""Chat service driving a PydanticAI ``Agent`` per conversation.

Phase 6 / Plan 06-04 (Wave 4): the Phase 5 monolithic ``ConversationStore``
collaborator splits into :class:`MessageStore` (events) and
:class:`ConversationRepository` (meta-CRUD) per CONTEXT.md D-05/D-06. The
``getattr(self._conversation_store, "_store", ...)`` peek (CR-04 from Phase 5
verification) retires here — the new
:meth:`MessageStore.first_user_message_preview` is owned by the ABC and both
impls (in-memory + Postgres) implement it directly.

Phase 5 / Plan 05-04 (Wave 3): the LangChain ``bind_tools`` / ``astream`` /
``additional_kwargs["reasoning_content"]`` substrate retired in favour of
PydanticAI's ``Agent.iter()`` per-node streaming surface. The previous
``self._histories: dict[str, InMemoryChatMessageHistory]`` was already replaced
by the Phase 5 :class:`ConversationStore`; in this plan it splits further.

Phase 6 / Plan 06-05a (Wave 5) renames the wire surface ``session`` →
``conversation`` per CONTEXT.md D-03. The local-variable name
``conversation_id`` is now the canonical token; the underlying
:class:`MessageStore` and :class:`ConversationRepository` accept
``conversation_id: UUID`` and we ``UUID(conversation_id)`` at the call site.

Preserved invariants:

- ``_metadata[conversation_id]["last_tool_invocation"]`` write inside the
  ``CallToolsNode`` branch — the Phase 4.7 retry endpoint depends on it
  (CONTEXT.md D-09).
- ``ErrorEvent.raw_detail = _scrub(str(exc))`` with ``_scrub`` from
  :mod:`app.llm.log_scrubbing` (Phase 4.7 contract).
- ``ChatService.cleanup_expired_conversations`` is ``async def`` (was already
  async since Phase 5 / Assumption A1; now awaits :class:`MessageStore`).
- New: catches :class:`ConversationConcurrentAppendError` from the Postgres
  message store and surfaces a clean :class:`ErrorEvent` (T-06-04-04) instead
  of letting the SQL error propagate to the SSE wire.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

from pydantic_ai import Agent
from pydantic_ai.messages import (
    FunctionToolCallEvent,
    FunctionToolResultEvent,
    ModelRequest,
    ModelResponse,
    PartDeltaEvent,
    PartStartEvent,
    TextPart,
    TextPartDelta,
    ThinkingPart,
    ThinkingPartDelta,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)

from app.chat.deps import ChatDeps
from app.chat.models import (
    ChatConversationHistoryResponse,
    ChatConversationInfo,
    ChatHistoryMessage,
    ContentEvent,
    ErrorCode,
    ErrorEvent,
    StreamEvent,
    ThinkingEvent,
    ToolCallEvent,
    ToolResultEvent,
)
from app.chat.store import ConversationConcurrentAppendError
from app.exceptions import APIError
from app.llm.log_scrubbing import _scrub

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from app.chat.repository import ConversationRepository
    from app.chat.store import MessageStore
    from app.llm.errors import ProbeError
    from app.llm.factory import LLMProviderFactory, SessionLLMConfig
    from app.tools.flight_client import FlightAPIClient


logger = logging.getLogger(__name__)


class ChatService:
    """Per-app chat service driving one PydanticAI ``Agent`` per conversation.

    Owns:

    - ``self._factory`` — per-app :class:`LLMProviderFactory`.
    - ``self._message_store`` — :class:`MessageStore` ABC (D-05); event
      append/load/delete + ``first_user_message_preview`` source for the
      sidebar UX.
    - ``self._conversation_repo`` — :class:`ConversationRepository` ABC (D-06);
      conversation meta-CRUD (create, get, list_for_user, bump_last_activity,
      delete). Phase 6 wires :class:`PostgresConversationRepository` in
      lifespan; tests inject :class:`InMemoryConversationRepository`.
    - ``self._agents`` — per-conversation ``Agent[ChatDeps, str]`` (D-10).
    - ``self._metadata`` — per-conversation in-process metadata
      (``provider``/``model``/``user_id``/``created_at``/``last_tool_invocation``).
    - ``self._last_activity`` — per-conversation monotonic timestamp for cleanup.

    The Phase 4.x monkey-patched tool-attribute back-door is gone (D-06);
    the flight client is held on this service and threaded through
    :class:`ChatDeps` once per turn inside :meth:`chat_stream`.
    """

    def __init__(
        self,
        flight_client: FlightAPIClient,
        factory: LLMProviderFactory,
        message_store: MessageStore,
        conversation_repo: ConversationRepository,
    ) -> None:
        """Initialize the chat service with its split collaborators (D-05, D-06, D-10).

        Args:
            flight_client: Flight API client; threaded into the agent via
                :class:`ChatDeps` once per chat turn.
            factory: Per-app :class:`LLMProviderFactory`. Conversations construct
                their own ``Agent`` via :meth:`create_session`.
            message_store: ABC-typed message-event store; Phase 6 in-memory
                for tests, Postgres in production.
            conversation_repo: ABC-typed conversation meta-CRUD repository;
                Phase 6 in-memory for tests, Postgres in production.
        """
        self._flight_client = flight_client
        self._factory = factory
        self._message_store = message_store
        self._conversation_repo = conversation_repo
        self._agents: dict[str, Agent[ChatDeps, str]] = {}
        # ``_metadata`` keys: ``provider``, ``model``, ``user_id``, ``created_at``,
        # and (set after a tool call) ``last_tool_invocation``.
        self._metadata: dict[str, dict[str, Any]] = {}
        self._last_activity: dict[str, float] = {}

    async def create_session(self, config: SessionLLMConfig, user_id: str) -> tuple[str, ProbeError | None]:
        """Create a new chat conversation: build provider, probe, build Agent, store.

        Note: the public-facing route renamed to ``create_conversation`` in
        Plan 06-05a; this internal method keeps its ``create_session`` name
        because ``SessionLLMConfig`` is the runtime-LLM-binding shape (the
        D-03 reserved-word boundary preserves the LLM-factory contract).

        Args:
            config: Per-conversation LLM configuration (provider/model/base_url/api_key).
            user_id: Authenticated username — used as the per-user partition key
                (D-22, D-27). Required.

        Returns:
            ``(conversation_id, None)`` on success; ``("", probe_error)`` when the
            provider's ``validate_config`` returns a structured ``ProbeError``.
        """
        provider = self._factory.build(config)
        probe_error = await provider.validate_config()
        if probe_error is not None:
            return "", probe_error

        # Lazy import to break the ``app.chat`` ↔ ``app.tools.flight_search``
        # circular import: ``flight_search`` annotates ``ctx: RunContext[ChatDeps]``
        # which means it must be importable AFTER ``app.chat.deps`` is loaded.
        # Since ``app.chat/__init__.py`` imports ``ChatService`` (this module),
        # eagerly importing ``search_flights`` at module load time triggers the
        # cycle. Resolving it lazily here happens AFTER ``__init__.py`` has
        # finished loading, so ``ChatDeps`` is fully available.
        from app.tools.flight_search import search_flights  # noqa: PLC0415

        agent = provider.build_agent(tools=[search_flights], deps_type=ChatDeps)
        conversation_id = str(uuid.uuid4())
        self._agents[conversation_id] = agent
        self._metadata[conversation_id] = {
            "provider": config.provider,
            "model": config.model,
            "user_id": user_id,
            "created_at": datetime.now(UTC).isoformat(),
        }
        self._last_activity[conversation_id] = time.time()
        return conversation_id, None

    async def list_conversations_for_user(self, user_id: str) -> list[ChatConversationInfo]:
        """Return ``ChatConversationInfo`` records for conversations owned by ``user_id``.

        Phase 6 / Plan 06-04: composes the conversation list from the in-process
        ``_metadata`` dict (keyed by ``conversation_id`` UUID-string) plus the new
        :meth:`MessageStore.first_user_message_preview`. The ``user_id`` here
        is still the wire-level username (the Phase 5 ``current_user.username``
        contract).

        Args:
            user_id: Authenticated username (Phase 5 partition key).

        Returns:
            Conversations owned by ``user_id``, sorted by last-activity desc.
        """
        results: list[ChatConversationInfo] = []
        for conversation_id, metadata in self._metadata.items():
            if metadata.get("user_id") != user_id:
                continue
            preview = await self._message_store.first_user_message_preview(UUID(conversation_id))
            results.append(
                ChatConversationInfo(
                    conversation_id=conversation_id,
                    provider=metadata["provider"],
                    model=metadata["model"],
                    created_at=metadata["created_at"],
                    first_message_preview=preview,
                )
            )
        # Sort by last activity so the conversation with the most recent message
        # appears first.
        results.sort(key=lambda info: self._last_activity.get(info.conversation_id, 0.0), reverse=True)
        return results

    async def _first_message_preview(self, conversation_id: str) -> str | None:
        """Return the first user message content (truncated to 80 chars), or None.

        Phase 6: delegates to :meth:`MessageStore.first_user_message_preview`
        (the canonical CR-04 fix from Phase 5 verification). The previous
        ``getattr(self._conversation_store, "_store", None)`` peek is gone —
        both in-memory and Postgres impls own this query directly.
        """
        return await self._message_store.first_user_message_preview(UUID(conversation_id))

    async def get_history_for_user(
        self, conversation_id: str, user_id: str
    ) -> ChatConversationHistoryResponse | None:
        """Return the conversation's user/assistant history, if owned by ``user_id``.

        Returns ``None`` when the conversation doesn't exist OR when ``user_id``
        is not the owner (mirrors the Phase 4.7 oracle-mitigation 404 shape).

        Maps PydanticAI :class:`ModelRequest`/:class:`ModelResponse` parts
        into the wire-level ``ChatHistoryMessage`` shape. ``UserPromptPart``
        → ``role="user"``; ``TextPart`` on a :class:`ModelResponse` →
        ``role="assistant"``. Tool-call/return parts and reasoning chunks
        are stream-only artefacts and are not surfaced here.
        """
        metadata = self._metadata.get(conversation_id)
        if metadata is None or metadata.get("user_id") != user_id:
            return None

        history_msgs = await self._message_store.load(UUID(conversation_id))

        messages: list[ChatHistoryMessage] = []
        for msg in history_msgs:
            if isinstance(msg, ModelRequest):
                for req_part in msg.parts:
                    if isinstance(req_part, UserPromptPart):
                        content = req_part.content if isinstance(req_part.content, str) else str(req_part.content)
                        messages.append(ChatHistoryMessage(role="user", content=content))
            elif isinstance(msg, ModelResponse):
                for resp_part in msg.parts:
                    if isinstance(resp_part, TextPart) and resp_part.content:
                        messages.append(ChatHistoryMessage(role="assistant", content=resp_part.content))
        return ChatConversationHistoryResponse(
            conversation_id=conversation_id,
            provider=metadata["provider"],
            model=metadata["model"],
            messages=messages,
        )

    async def cleanup_expired_conversations(self, max_age_seconds: int = 3600) -> int:
        """Remove expired conversations across all per-conversation dicts and the message store.

        Args:
            max_age_seconds: Maximum age since last activity (default: 1 hour).

        Returns:
            Number of conversations cleaned up.

        Async because :meth:`MessageStore.delete` is async; per-conversation
        truncation only — the conversation row itself stays put.
        """
        now = time.time()
        expired = [cid for cid, last_active in self._last_activity.items() if now - last_active > max_age_seconds]

        for conversation_id in expired:
            await self._message_store.delete(UUID(conversation_id))
            self._metadata.pop(conversation_id, None)
            self._agents.pop(conversation_id, None)
            self._last_activity.pop(conversation_id, None)

        return len(expired)

    async def delete_conversation(self, conversation_id: str) -> None:
        """Remove a single conversation. Used by ``DELETE /api/chat/conversation/{id}``.

        The route layer enforces ownership before calling this; this method
        simply tears down the per-conversation state. ``MessageStore.delete``
        is a no-op for unknown ``conversation_id``s, mirroring the
        ``_metadata.pop(..., None)`` shape.
        """
        await self._message_store.delete(UUID(conversation_id))
        self._metadata.pop(conversation_id, None)
        self._agents.pop(conversation_id, None)
        self._last_activity.pop(conversation_id, None)

    async def chat_stream(
        self, message: str, conversation_id: str, *, persist_user_message: bool = True
    ) -> AsyncGenerator[StreamEvent]:
        """Stream a chat response chunk by chunk, driving PydanticAI ``agent.iter()``.

        Per RESEARCH §3 streaming, the per-node loop walks the agent graph and
        maps PydanticAI events to the four ``StreamEvent`` subclasses:

        - :class:`PartStartEvent` + :class:`ThinkingPart` → :class:`ThinkingEvent`.
        - :class:`PartDeltaEvent` + :class:`ThinkingPartDelta` → :class:`ThinkingEvent`.
        - :class:`PartStartEvent` + :class:`TextPart` → :class:`ContentEvent`.
        - :class:`PartDeltaEvent` + :class:`TextPartDelta` → :class:`ContentEvent`.
        - :class:`FunctionToolCallEvent` → :class:`ToolCallEvent` (also writes
          ``_metadata[conversation_id]["last_tool_invocation"]`` for the retry endpoint).
        - :class:`FunctionToolResultEvent` carrying :class:`ToolReturnPart` →
          :class:`ToolResultEvent`.

        On any exception inside the iter-loop, emit a single
        :class:`ErrorEvent` with ``raw_detail = _scrub(str(exc))`` and return
        early (the Phase 4.7 contract). Phase 6 / Plan 06-04 additionally
        catches :class:`ConversationConcurrentAppendError` from the Postgres
        message store (T-06-04-04) and surfaces a clean retryable
        ``stream_error`` ErrorEvent rather than letting the SQL error
        propagate (PATTERNS.md §Logging-with-scrubber).

        After the run completes cleanly, append
        ``agent_run.result.new_messages()`` to the message store, then bump
        the conversation's ``last_activity_at`` so the user-scoped sidebar
        reorders correctly. ``persist_user_message=False`` skips the persist
        step (used by the retry endpoint).

        Args:
            message: User message.
            conversation_id: Conversation ID for continuity.
            persist_user_message: When False, the run's new messages are NOT
                appended to the message store (synthetic retry prompts shouldn't
                accumulate in stored history).
        """
        history = await self._message_store.load(UUID(conversation_id))
        deps = ChatDeps(
            flight_client=self._flight_client,
            conversation_id=conversation_id,
            user_id=self._metadata[conversation_id]["user_id"],
        )
        agent = self._agents[conversation_id]
        # Track per-tool-call timing so ToolResultEvent.elapsed_ms reflects
        # the wall-clock between the FunctionToolCallEvent and its result.
        tool_call_start: dict[str, float] = {}

        try:
            async with agent.iter(message, message_history=history, deps=deps) as agent_run:
                async for node in agent_run:
                    if Agent.is_model_request_node(node):
                        async with node.stream(agent_run.ctx) as model_stream:
                            async for event in model_stream:
                                stream_event = self._map_model_request_event(event, conversation_id)
                                if stream_event is not None:
                                    yield stream_event
                    elif Agent.is_call_tools_node(node):
                        async with node.stream(agent_run.ctx) as tool_stream:
                            async for ev in tool_stream:
                                async for stream_event in self._handle_tool_event(
                                    ev, conversation_id, tool_call_start
                                ):
                                    yield stream_event

            if persist_user_message and agent_run.result is not None:
                conversation_uuid = UUID(conversation_id)
                await self._message_store.append(conversation_uuid, agent_run.result.new_messages())
                # Bump conversation activity AFTER a successful append so the
                # user-scoped sidebar reorders. No-op when the conversation
                # row doesn't exist yet.
                await self._conversation_repo.bump_last_activity(conversation_uuid)
            self._last_activity[conversation_id] = time.time()
        except ConversationConcurrentAppendError as exc:
            # T-06-04-04: log full exception server-side via the scrubber-
            # filtered logger, surface a static retryable ErrorEvent on the
            # SSE wire (PATTERNS.md §Logging-with-scrubber).
            logger.exception("ConversationConcurrentAppendError on conversation %s", conversation_id)
            yield ErrorEvent(
                error_code=ErrorCode.stream_error,
                message="Sorry, the conversation got out of sync — please try again.",
                retryable=True,
                tool_name=None,
                raw_detail=_scrub(str(exc)),
                conversation_id=conversation_id,
            )
        except APIError as exc:
            # Tool body or downstream APIError — preserve Phase 4.7 retryable shape.
            yield ErrorEvent(
                error_code=ErrorCode.tool_error,
                message=f"Chat stream failed: {exc.message}",
                retryable=exc.retryable,
                tool_name=None,
                raw_detail=_scrub(str(exc)),
                conversation_id=conversation_id,
            )
        except Exception as exc:
            yield ErrorEvent(
                error_code=ErrorCode.stream_error,
                message="Chat stream failed.",
                retryable=False,
                tool_name=None,
                raw_detail=_scrub(str(exc)),
                conversation_id=conversation_id,
            )

    @staticmethod
    def _map_model_request_event(event: Any, conversation_id: str) -> StreamEvent | None:
        """Map a PydanticAI ``ModelRequestNode.stream`` event to a StreamEvent.

        Returns ``None`` for empty/uninteresting events (so the caller does
        not yield a no-op chunk). Match-block per RESEARCH §3 Stream Event
        Type Map.
        """
        if isinstance(event, PartStartEvent):
            part = event.part
            if isinstance(part, ThinkingPart) and part.content:
                return ThinkingEvent(chunk=part.content, conversation_id=conversation_id)
            if isinstance(part, TextPart) and part.content:
                return ContentEvent(chunk=part.content, conversation_id=conversation_id)
        elif isinstance(event, PartDeltaEvent):
            delta = event.delta
            if isinstance(delta, ThinkingPartDelta) and delta.content_delta:
                return ThinkingEvent(chunk=delta.content_delta, conversation_id=conversation_id)
            if isinstance(delta, TextPartDelta) and delta.content_delta:
                return ContentEvent(chunk=delta.content_delta, conversation_id=conversation_id)
        return None

    async def _handle_tool_event(
        self,
        event: Any,
        conversation_id: str,
        tool_call_start: dict[str, float],
    ) -> AsyncGenerator[StreamEvent]:
        """Map a PydanticAI ``CallToolsNode.stream`` event to StreamEvents.

        ``FunctionToolCallEvent`` carries a :class:`ToolCallPart`; its
        ``args`` may be a dict or a JSON string (RESEARCH Pitfall 3) — we
        normalise to dict before yielding the ``ToolCallEvent``. The same
        event triggers the ``_metadata[conversation_id]["last_tool_invocation"]``
        write that the Phase 4.7 retry endpoint depends on (D-09).

        ``FunctionToolResultEvent`` carrying a :class:`ToolReturnPart` is
        mapped to a :class:`ToolResultEvent` whose ``elapsed_ms`` is the
        wall-clock between the call and the result; we look up the start
        timestamp via ``tool_call_id`` so multiple concurrent tool calls
        keep their own timing.
        """
        if isinstance(event, FunctionToolCallEvent):
            part: ToolCallPart = event.part
            tool_args = part.args if isinstance(part.args, dict) else json.loads(part.args or "{}")
            tool_call_start[part.tool_call_id] = time.monotonic()

            # Preserved invariant (D-09): the retry endpoint reads this back.
            self._metadata[conversation_id]["last_tool_invocation"] = {
                "tool_name": part.tool_name,
                "tool_args": tool_args,
                "tool_call_id": part.tool_call_id,
            }

            yield ToolCallEvent(
                tool_name=part.tool_name,
                tool_args=tool_args,
                conversation_id=conversation_id,
            )
        elif isinstance(event, FunctionToolResultEvent):
            # ``event.part`` is the new (1.x) attribute; ``event.result`` is the
            # deprecated alias. Match the current spelling to avoid the
            # ``DeprecationWarning`` and make Phase 8 structlog cleaner.
            ret = event.part
            if isinstance(ret, ToolReturnPart):
                started = tool_call_start.pop(ret.tool_call_id, None)
                elapsed_ms = int((time.monotonic() - started) * 1000) if started is not None else 0
                yield ToolResultEvent(
                    tool_name=ret.tool_name,
                    tool_result=str(ret.content),
                    elapsed_ms=elapsed_ms,
                    conversation_id=conversation_id,
                )
