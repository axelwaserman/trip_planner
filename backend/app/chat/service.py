"""Chat service driving a PydanticAI ``Agent`` per session.

Phase 5 / Plan 05-04 (Wave 3): the LangChain ``bind_tools`` / ``astream`` /
``additional_kwargs["reasoning_content"]`` substrate retired here in favour of
PydanticAI's ``Agent.iter()`` per-node streaming surface. The previous
``self._histories: dict[str, InMemoryChatMessageHistory]`` is replaced by a
:class:`ConversationStore` seam (D-08); the previous
``self._bound_providers: dict[str, BoundProvider]`` is replaced by
``self._agents: dict[str, Agent[ChatDeps, str]]`` (D-10). The Phase 4.x
monkey-patched tool-attribute back-door is gone — the flight client is
threaded through PydanticAI's :class:`RunContext` via :class:`ChatDeps`.

Preserved invariants:

- ``_metadata[session_id]["last_tool_invocation"]`` write inside the
  ``CallToolsNode`` branch — the Phase 4.7 retry endpoint depends on it
  (CONTEXT.md D-09).
- ``ErrorEvent.raw_detail = _scrub(str(exc))`` with ``_scrub`` from
  :mod:`app.llm.log_scrubbing` (Phase 4.7 contract).
- ``ChatService.cleanup_expired_sessions`` flips to ``async def`` because it
  now ``await``\\s :meth:`ConversationStore.delete` (RESEARCH Assumption A1).
"""

from __future__ import annotations

import json
import time
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from pydantic_ai import Agent
from pydantic_ai.messages import (
    FunctionToolCallEvent,
    FunctionToolResultEvent,
    ModelRequest,
    ModelResponse,
    PartDeltaEvent,
    PartStartEvent,
    RetryPromptPart,
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
    ChatHistoryMessage,
    ChatSessionHistoryResponse,
    ChatSessionInfo,
    ContentEvent,
    ErrorCode,
    ErrorEvent,
    StreamEvent,
    ThinkingEvent,
    ToolCallEvent,
    ToolResultEvent,
)
from app.exceptions import APIError
from app.llm.log_scrubbing import _scrub

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from app.chat.store import ConversationStore
    from app.llm.errors import ProbeError
    from app.llm.factory import LLMProviderFactory, SessionLLMConfig
    from app.tools.flight_client import FlightAPIClient


class ChatService:
    """Per-app chat service driving one PydanticAI ``Agent`` per session.

    Owns:

    - ``self._factory`` — per-app :class:`LLMProviderFactory`.
    - ``self._conversation_store`` — :class:`ConversationStore` ABC (D-08);
      Phase 5 wires :class:`InMemoryConversationStore`, Phase 6 swaps for SQL.
    - ``self._agents`` — per-session ``Agent[ChatDeps, str]`` (D-10).
    - ``self._metadata`` — per-session metadata
      (``provider``/``model``/``user_id``/``created_at``/``last_tool_invocation``).
    - ``self._last_activity`` — per-session monotonic timestamp for cleanup.

    The Phase 4.x monkey-patched tool-attribute back-door is gone (D-06);
    the flight client is held on this service and threaded through
    :class:`ChatDeps` once per turn inside :meth:`chat_stream`.
    """

    def __init__(
        self,
        flight_client: FlightAPIClient,
        factory: LLMProviderFactory,
        conversation_store: ConversationStore,
    ) -> None:
        """Initialize the chat service with collaborators (D-08, D-10).

        Args:
            flight_client: Flight API client; threaded into the agent via
                :class:`ChatDeps` once per chat turn.
            factory: Per-app :class:`LLMProviderFactory`. Sessions construct
                their own ``Agent`` via :meth:`create_session`.
            conversation_store: ABC-typed history store; Phase 5 in-memory,
                Phase 6 Postgres.
        """
        self._flight_client = flight_client
        self._factory = factory
        self._conversation_store = conversation_store
        self._agents: dict[str, Agent[ChatDeps, str]] = {}
        # ``_metadata`` keys: ``provider``, ``model``, ``user_id``, ``created_at``,
        # and (set after a tool call) ``last_tool_invocation``.
        self._metadata: dict[str, dict[str, Any]] = {}
        self._last_activity: dict[str, float] = {}

    async def create_session(self, config: SessionLLMConfig, user_id: str) -> tuple[str, ProbeError | None]:
        """Create a new chat session: build provider, probe, build Agent, store.

        Args:
            config: Per-session LLM configuration (provider/model/base_url/api_key).
            user_id: Authenticated username — used as the session-partition key
                (D-22, D-27). Required.

        Returns:
            ``(session_id, None)`` on success; ``("", probe_error)`` when the
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
        session_id = str(uuid.uuid4())
        self._agents[session_id] = agent
        self._metadata[session_id] = {
            "provider": config.provider,
            "model": config.model,
            "user_id": user_id,
            "created_at": datetime.now(UTC).isoformat(),
        }
        self._last_activity[session_id] = time.time()
        return session_id, None

    def is_conversation_owner(self, session_id: str, user_id: str) -> bool:
        """Return True when ``user_id`` owns ``session_id``.

        Used by route ownership checks (H7) to avoid direct ``_metadata``
        access from the route layer. Returns False for missing sessions so the
        route can issue the same 404 shape for missing-vs-not-owner, preventing
        session-existence probing.

        Args:
            session_id: Session UUID to check.
            user_id: Authenticated username (the JWT ``sub`` claim).
        """
        return self._metadata.get(session_id, {}).get("user_id") == user_id

    def get_conversation_metadata(self, session_id: str) -> dict[str, Any] | None:
        """Return raw metadata dict for ``session_id``, or None if absent.

        Used by the ``create_session`` route to read provider/model back after a
        successful :meth:`create_session` call without crossing the
        ``_metadata`` encapsulation boundary (H7). Not to be used for ownership
        decisions — use :meth:`is_conversation_owner` for that.

        Args:
            session_id: Session UUID to look up.
        """
        return self._metadata.get(session_id)

    def list_sessions_for_user(self, user_id: str) -> list[ChatSessionInfo]:
        """Return ``ChatSessionInfo`` records for sessions owned by ``user_id``.

        Phase 5: ``first_message_preview`` is composed from the in-memory
        store's ``_store`` dict (synchronous access). Per CONTEXT.md D-09 the
        store does NOT track session metadata; this method joins ``_metadata``
        (provider/model/created_at) with the store's per-session message list.

        ``list_for_user`` on the in-memory store returns an empty list (the
        store does not own the user→sessions index in Phase 5); this method
        composes the user-scoped view from ``_metadata`` filtered by
        ``user_id`` — same behaviour as Phase 4.7, just routed through the
        store seam for Phase 6 swappability.
        """
        results: list[ChatSessionInfo] = []
        for session_id, metadata in self._metadata.items():
            if metadata.get("user_id") != user_id:
                continue
            results.append(
                ChatSessionInfo(
                    session_id=session_id,
                    provider=metadata["provider"],
                    model=metadata["model"],
                    created_at=metadata["created_at"],
                    first_message_preview=self._get_first_message_preview(session_id),
                )
            )
        # Sort by last activity so the session with the most recent message
        # appears first.
        results.sort(key=lambda info: self._last_activity.get(info.session_id, 0.0), reverse=True)
        return results

    def _get_first_message_preview(self, session_id: str) -> str | None:
        """Return the first user message content (truncated to 80 chars), or None.

        Walks the in-memory store's stored ``ModelMessage`` list synchronously
        — the in-memory impl never blocks. Phase 6's PG impl will require this
        to become ``async``; ``list_sessions_for_user`` will flip with it.
        """
        # Defensive: read from the underlying ``_store`` dict to keep this method
        # synchronous. The in-memory impl exposes ``_store`` as a dict; an
        # ``AttributeError`` here means a non-in-memory impl was injected and
        # the caller (or Phase 6) should rewrite this to ``async``.
        store_dict = getattr(self._conversation_store, "_store", None)
        if store_dict is None:
            return None
        messages = store_dict.get(session_id, [])
        for msg in messages:
            if isinstance(msg, ModelRequest):
                for part in msg.parts:
                    if isinstance(part, UserPromptPart):
                        content = part.content
                        if isinstance(content, str):
                            return content[:80]
                        return str(content)[:80]
        return None

    def get_history_for_user(self, session_id: str, user_id: str) -> ChatSessionHistoryResponse | None:
        """Return the session's user/assistant history, if owned by ``user_id``.

        Returns ``None`` when the session doesn't exist OR when ``user_id``
        is not the owner (mirrors the Phase 4.7 oracle-mitigation 404 shape).

        Maps PydanticAI :class:`ModelRequest`/:class:`ModelResponse` parts
        into the wire-level ``ChatHistoryMessage`` shape. ``UserPromptPart``
        → ``role="user"``; ``TextPart`` on a :class:`ModelResponse` →
        ``role="assistant"``. Tool-call/return parts and reasoning chunks
        are stream-only artefacts and are not surfaced here.
        """
        metadata = self._metadata.get(session_id)
        if metadata is None or metadata.get("user_id") != user_id:
            return None

        store_dict = getattr(self._conversation_store, "_store", None)
        history_msgs = store_dict.get(session_id, []) if store_dict is not None else []

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
        return ChatSessionHistoryResponse(
            session_id=session_id,
            provider=metadata["provider"],
            model=metadata["model"],
            messages=messages,
        )

    async def cleanup_expired_sessions(self, max_age_seconds: int = 3600) -> int:
        """Remove expired sessions across all per-session dicts and the store.

        Args:
            max_age_seconds: Maximum age since last activity (default: 1 hour).

        Returns:
            Number of sessions cleaned up.

        Async because :meth:`ConversationStore.delete` is async (RESEARCH
        Assumption A1).
        """
        now = time.time()
        expired = [sid for sid, last_active in self._last_activity.items() if now - last_active > max_age_seconds]

        for session_id in expired:
            await self._conversation_store.delete(session_id)
            self._metadata.pop(session_id, None)
            self._agents.pop(session_id, None)
            self._last_activity.pop(session_id, None)

        return len(expired)

    async def delete_session(self, session_id: str) -> None:
        """Remove a single session. Used by ``DELETE /api/chat/session/{id}``.

        The route layer enforces ownership before calling this; this method
        simply tears down the per-session state. ``ConversationStore.delete``
        is a no-op for unknown ``session_id``s, mirroring the
        ``_metadata.pop(..., None)`` shape.
        """
        await self._conversation_store.delete(session_id)
        self._metadata.pop(session_id, None)
        self._agents.pop(session_id, None)
        self._last_activity.pop(session_id, None)

    async def chat_stream(
        self, message: str, session_id: str, *, persist_user_message: bool = True
    ) -> AsyncGenerator[StreamEvent]:
        """Stream a chat response chunk by chunk, driving PydanticAI ``agent.iter()``.

        Per RESEARCH §3 streaming, the per-node loop walks the agent graph and
        maps PydanticAI events to the four ``StreamEvent`` subclasses:

        - :class:`PartStartEvent` + :class:`ThinkingPart` → :class:`ThinkingEvent`.
        - :class:`PartDeltaEvent` + :class:`ThinkingPartDelta` → :class:`ThinkingEvent`.
        - :class:`PartStartEvent` + :class:`TextPart` → :class:`ContentEvent`.
        - :class:`PartDeltaEvent` + :class:`TextPartDelta` → :class:`ContentEvent`.
        - :class:`FunctionToolCallEvent` → :class:`ToolCallEvent` (also writes
          ``_metadata[session_id]["last_tool_invocation"]`` for the retry endpoint).
        - :class:`FunctionToolResultEvent` carrying :class:`ToolReturnPart` →
          :class:`ToolResultEvent`.

        On any exception inside the iter-loop, emit a single
        :class:`ErrorEvent` with ``raw_detail = _scrub(str(exc))`` and return
        early (the Phase 4.7 contract).

        After the run completes cleanly, append
        ``agent_run.result.new_messages()`` to the conversation store so the
        next turn sees the full history. ``persist_user_message=False`` skips
        the persist step (used by the retry endpoint).

        Args:
            message: User message.
            session_id: Session ID for conversation continuity.
            persist_user_message: When False, the run's new messages are NOT
                appended to the store (synthetic retry prompts shouldn't
                accumulate in stored history).
        """
        # C1: guard against TOCTOU race where the session was deleted between the
        # route's ownership check and this generator's first line. Both _metadata
        # and _agents must be present; yield a session_error ErrorEvent and return
        # rather than letting the KeyError propagate as a 500.
        try:
            user_id_val = self._metadata[session_id]["user_id"]
            agent = self._agents[session_id]
        except KeyError:
            yield ErrorEvent(
                error_code=ErrorCode.session_error,
                message="Conversation not found or expired.",
                retryable=False,
                tool_name=None,
                raw_detail=None,
                session_id=session_id,
            )
            return

        history = await self._conversation_store.load(session_id)
        deps = ChatDeps(
            flight_client=self._flight_client,
            session_id=session_id,
            user_id=user_id_val,
        )
        # Track per-tool-call timing so ToolResultEvent.elapsed_ms reflects
        # the wall-clock between the FunctionToolCallEvent and its result.
        tool_call_start: dict[str, float] = {}

        try:
            # H3: capture new_messages INSIDE the async-with block so the result
            # is available after the context manager exits. Accessing
            # agent_run.result OUTSIDE the block is unsafe — the result object
            # may have been cleaned up by the time the context manager teardown
            # runs (PydanticAI RESEARCH Pitfall 5).
            _new_messages: list[Any] = []
            async with agent.iter(message, message_history=history, deps=deps) as agent_run:
                async for node in agent_run:
                    if Agent.is_model_request_node(node):
                        async with node.stream(agent_run.ctx) as model_stream:
                            async for event in model_stream:
                                stream_event = self._map_model_request_event(event, session_id)
                                if stream_event is not None:
                                    yield stream_event
                    elif Agent.is_call_tools_node(node):
                        async with node.stream(agent_run.ctx) as tool_stream:
                            async for ev in tool_stream:
                                async for stream_event in self._handle_tool_event(ev, session_id, tool_call_start):
                                    yield stream_event
                # Capture new_messages before the async-with context closes (H3).
                if agent_run.result is not None:
                    _new_messages = agent_run.result.new_messages()

            if persist_user_message and _new_messages:
                await self._conversation_store.append(session_id, _new_messages)
            self._last_activity[session_id] = time.time()
        except APIError as exc:
            # Tool body or downstream APIError — preserve Phase 4.7 retryable shape.
            yield ErrorEvent(
                error_code=ErrorCode.tool_error,
                message=f"Chat stream failed: {exc.message}",
                retryable=exc.retryable,
                tool_name=None,
                raw_detail=_scrub(str(exc)),
                session_id=session_id,
            )
        except Exception as exc:
            yield ErrorEvent(
                error_code=ErrorCode.stream_error,
                message="Chat stream failed.",
                retryable=False,
                tool_name=None,
                raw_detail=_scrub(str(exc)),
                session_id=session_id,
            )

    @staticmethod
    def _map_model_request_event(event: Any, session_id: str) -> StreamEvent | None:
        """Map a PydanticAI ``ModelRequestNode.stream`` event to a StreamEvent.

        Returns ``None`` for empty/uninteresting events (so the caller does
        not yield a no-op chunk). Match-block per RESEARCH §3 Stream Event
        Type Map.
        """
        if isinstance(event, PartStartEvent):
            part = event.part
            if isinstance(part, ThinkingPart) and part.content:
                return ThinkingEvent(chunk=part.content, session_id=session_id)
            if isinstance(part, TextPart) and part.content:
                return ContentEvent(chunk=part.content, session_id=session_id)
        elif isinstance(event, PartDeltaEvent):
            delta = event.delta
            if isinstance(delta, ThinkingPartDelta) and delta.content_delta:
                return ThinkingEvent(chunk=delta.content_delta, session_id=session_id)
            if isinstance(delta, TextPartDelta) and delta.content_delta:
                return ContentEvent(chunk=delta.content_delta, session_id=session_id)
        return None

    async def _handle_tool_event(
        self,
        event: Any,
        session_id: str,
        tool_call_start: dict[str, float],
    ) -> AsyncGenerator[StreamEvent]:
        """Map a PydanticAI ``CallToolsNode.stream`` event to StreamEvents.

        ``FunctionToolCallEvent`` carries a :class:`ToolCallPart`; its
        ``args`` may be a dict or a JSON string (RESEARCH Pitfall 3) — we
        normalise to dict before yielding the ``ToolCallEvent``. The same
        event triggers the ``_metadata[session_id]["last_tool_invocation"]``
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
            self._metadata[session_id]["last_tool_invocation"] = {
                "tool_name": part.tool_name,
                "tool_args": tool_args,
                "tool_call_id": part.tool_call_id,
            }

            yield ToolCallEvent(
                tool_name=part.tool_name,
                tool_args=tool_args,
                session_id=session_id,
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
                    session_id=session_id,
                )
            elif isinstance(ret, RetryPromptPart):
                # C4: RetryPromptPart means the tool returned an error that asks
                # the model to retry. Pop the timing entry to avoid a memory leak
                # (best-effort: tool_call_id may differ from the original call-id
                # in some edge cases, so we use .pop(..., None) defensively).
                tool_call_start.pop(ret.tool_call_id, None)
                yield ErrorEvent(
                    error_code=ErrorCode.tool_error,
                    message="Tool requested a retry.",
                    retryable=True,
                    tool_name=ret.tool_name,
                    raw_detail=None,
                    session_id=session_id,
                )
