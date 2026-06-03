"""Chat service using LangChain with tool calling.

Per Phase 4.5 Plan 06, ``ChatService`` no longer holds a singleton bound LLM.
Instead, it owns a per-app :class:`app.llm.factory.LLMProviderFactory` and a
``self._bound_providers`` dict keyed by ``session_id``. ``create_session`` is
``async`` because it absorbs the 4.2 provider-probe step (now per-provider via
:meth:`app.llm.base.LLMProvider.validate_config`) — the sequence is
``factory.build → validate_config → bind_tools → store``.

The 4.2 default fallbacks (``provider="ollama"``, ``model="qwen3:4b"``) live
in the route layer (``app.api.routes.routes.create_session``); the
:class:`app.llm.factory.SessionLLMConfig` dataclass requires both fields to be
non-``None`` at construction.

Phase 4.7: ChatService now yields concrete event classes
(ContentEvent, ThinkingEvent, ToolCallEvent, ToolResultEvent, ErrorEvent) instead
of the monolithic StreamEvent, and wraps tool execution in APIError / Exception
handlers that yield ErrorEvent and return early. After each tool_call yield,
``_metadata[session_id]["last_tool_invocation"]`` is stored for the retry endpoint
(Plan 02, D-07).
"""

from __future__ import annotations

import time
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from langchain_core.chat_history import InMemoryChatMessageHistory
from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage, HumanMessage

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
from app.tools.flight_search import search_flights

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from app.llm.errors import ProbeError
    from app.llm.factory import LLMProviderFactory, SessionLLMConfig
    from app.tools.flight_client import FlightAPIClient


class ChatService:
    """Service for managing chat conversations with LangChain and tool calling.

    Owns a per-app :class:`LLMProviderFactory` plus a per-session bound provider
    cache. ``create_session`` is ``async`` and runs the provider probe inline;
    on probe success the bound provider is stashed in ``self._bound_providers``
    keyed by ``session_id`` and consumed by :meth:`chat_stream`.
    """

    def __init__(self, flight_client: FlightAPIClient, factory: LLMProviderFactory) -> None:
        """Initialize the chat service with flight client and LLM factory.

        Args:
            flight_client: Flight API client injected into the search_flights tool.
            factory: Per-app :class:`LLMProviderFactory`. Sessions construct
                their own bound provider via :meth:`create_session`.
        """
        self._factory = factory
        self._histories: dict[str, InMemoryChatMessageHistory] = {}
        self._metadata: dict[str, dict[str, Any]] = {}  # Session metadata; widens to Any for last_tool_invocation
        # Wave 3 (plan 05-04) replaces this dict with ``self._agents: dict[str, Agent]``;
        # the value type is ``Any`` here because the Phase 4.5 second-tier provider
        # Protocol retired in plan 05-02 (D-01..D-03) and the PydanticAI ``Agent``
        # swap is Wave 3.
        self._bound_providers: dict[str, Any] = {}
        self._last_activity: dict[str, float] = {}

        # Wire the tool's client dependency here so callers don't need to know internals
        search_flights._flight_client = flight_client  # type: ignore[attr-defined]

    async def create_session(self, config: SessionLLMConfig, user_id: str) -> tuple[str, ProbeError | None]:
        """Create a new chat session: build provider, probe, bind tools, store.

        Args:
            config: Per-session LLM configuration (provider/model/base_url/api_key).
            user_id: Authenticated username — used as the session-partition key
                (D-22, D-27; RESEARCH.md Open Question 5 RESOLVED). Required.

        Returns:
            ``(session_id, None)`` on success; ``("", probe_error)`` when the
            provider's ``validate_config`` returns a structured ``ProbeError``.
            The route layer maps the error to an HTTP status (502 for
            ``PROVIDER_UNREACHABLE``, 400 for everything else).
        """
        provider = self._factory.build(config)
        probe_error = await provider.validate_config()
        if probe_error is not None:
            return "", probe_error

        bound = provider.bind_tools([search_flights])
        session_id = str(uuid.uuid4())
        self._histories[session_id] = InMemoryChatMessageHistory()
        self._bound_providers[session_id] = bound
        self._metadata[session_id] = {
            "provider": config.provider,
            "model": config.model,
            "user_id": user_id,
            "created_at": datetime.now(UTC).isoformat(),
        }
        self._last_activity[session_id] = time.time()
        return session_id, None

    def list_sessions_for_user(self, user_id: str) -> list[ChatSessionInfo]:
        """Return ``ChatSessionInfo`` records for sessions owned by ``user_id``.

        Sessions are partitioned by ``_metadata[session_id]["user_id"]``
        (D-22, D-27; RESEARCH.md Open Question 5 RESOLVED — partition now,
        not at the Phase 5 PG migration). ``first_message_preview`` is the
        first ``HumanMessage`` content truncated to 80 chars, or ``None``
        when the history is empty. Results are sorted newest-first by
        ``created_at`` so the sidebar's reverse-chronological order is the
        natural default.
        """
        results: list[ChatSessionInfo] = []
        for session_id, metadata in self._metadata.items():
            if metadata.get("user_id") != user_id:
                continue
            history = self._histories.get(session_id)
            preview: str | None = None
            if history is not None:
                for msg in history.messages:
                    if isinstance(msg, HumanMessage):
                        content = msg.content if isinstance(msg.content, str) else str(msg.content)
                        preview = content[:80]
                        break
            results.append(
                ChatSessionInfo(
                    session_id=session_id,
                    provider=metadata["provider"],
                    model=metadata["model"],
                    created_at=metadata["created_at"],
                    first_message_preview=preview,
                )
            )
        # Sort by last activity so the session with the most recent message
        # appears first — more useful than creation time when the user has
        # replied to an older conversation.
        results.sort(key=lambda info: self._last_activity.get(info.session_id, 0.0), reverse=True)
        return results

    def get_history_for_user(self, session_id: str, user_id: str) -> ChatSessionHistoryResponse | None:
        """Return the session's user/assistant history, if owned by ``user_id``.

        Returns ``None`` when the session doesn't exist OR when ``user_id``
        is not the owner. Both paths collapse to the same return so the route
        layer can map both to ``404 Not Found`` — leaking ``403 vs 404``
        would be a session-existence oracle (same threat-model rationale as
        ``DELETE /api/chat/session/{id}``).

        Only ``HumanMessage`` and ``AIMessage`` entries are surfaced; tool
        execution traces and reasoning chunks are stream-only artefacts and
        don't round-trip cleanly through the chat history's serialised form.
        """
        metadata = self._metadata.get(session_id)
        if metadata is None or metadata.get("user_id") != user_id:
            return None
        history = self._histories.get(session_id)
        messages: list[ChatHistoryMessage] = []
        if history is not None:
            for msg in history.messages:
                if isinstance(msg, HumanMessage):
                    content = msg.content if isinstance(msg.content, str) else str(msg.content)
                    messages.append(ChatHistoryMessage(role="user", content=content))
                elif isinstance(msg, AIMessage):
                    content = msg.content if isinstance(msg.content, str) else str(msg.content)
                    if content:  # Skip empty AIMessages emitted only for tool calls.
                        messages.append(ChatHistoryMessage(role="assistant", content=content))
        return ChatSessionHistoryResponse(
            session_id=session_id,
            provider=metadata["provider"],
            model=metadata["model"],
            messages=messages,
        )

    def get_session_history(self, session_id: str) -> InMemoryChatMessageHistory:
        """Get history for a session.

        Args:
            session_id: Session identifier

        Returns:
            Chat history for the session

        Raises:
            ValueError: If session does not exist
        """
        if session_id in self._histories:
            self._last_activity[session_id] = time.time()
            return self._histories[session_id]
        raise ValueError(f"Session {session_id} not found")

    def cleanup_expired_sessions(self, max_age_seconds: int = 3600) -> int:
        """Remove expired sessions based on inactivity.

        Args:
            max_age_seconds: Maximum age since last activity (default: 1 hour)

        Returns:
            Number of sessions cleaned up
        """
        now = time.time()
        expired = [sid for sid, last_active in self._last_activity.items() if now - last_active > max_age_seconds]

        for session_id in expired:
            self._histories.pop(session_id, None)
            self._metadata.pop(session_id, None)
            self._bound_providers.pop(session_id, None)
            self._last_activity.pop(session_id, None)

        return len(expired)

    async def chat_stream(
        self, message: str, session_id: str, *, persist_user_message: bool = True
    ) -> AsyncGenerator[StreamEvent]:
        """Stream a chat response chunk by chunk with tool calling support.

        Yields concrete event classes (ContentEvent, ThinkingEvent, ToolCallEvent,
        ToolResultEvent, ErrorEvent). Tool execution is wrapped in APIError /
        Exception handlers — on error an ErrorEvent is yielded and the generator
        returns early. ``_metadata[session_id]["last_tool_invocation"]`` is stored
        after each tool_call yield for the Plan 02 retry endpoint (D-07).

        Args:
            message: User message
            session_id: Session ID for conversation continuity
            persist_user_message: When False the message is included in the
                LLM context but NOT appended to the session history.  Used by
                the retry endpoint so synthetic "Please retry…" prompts don't
                accumulate in the stored conversation.

        Yields:
            Concrete event objects (discriminated union members of StreamEvent)
        """
        history = self.get_session_history(session_id)
        bound = self._bound_providers[session_id]

        # Build messages with history
        history_messages: list[BaseMessage] = list(history.messages)
        messages: list[BaseMessage] = [*history_messages, HumanMessage(content=message)]

        # Persist the user turn upfront so a switch-conversations / disconnect
        # mid-stream still leaves the history complete on resume. The previous
        # behaviour appended user + assistant only at end-of-stream — if the
        # client disconnected (e.g. switched to a different chat in the
        # Sidebar), the history's view of "what just happened" was empty.
        # Skipped for synthetic retry prompts (persist_user_message=False) so
        # repeated retries don't corrupt the stored conversation history.
        if persist_user_message:
            history.add_user_message(message)

        # Track state
        tool_was_called = False
        accumulated_content = ""
        tool_call_message = None
        tool_results = []
        stream_completed_cleanly = False

        try:
            # Stream LLM response. We accumulate every chunk so that tool call
            # arguments — which arrive as partial JSON tokens across many chunks
            # via tool_call_chunks — are fully assembled before we process them.
            # Content and thinking events are still emitted in real-time.
            accumulated_chunk: AIMessageChunk | None = None
            async for chunk in bound.astream(messages):
                if not isinstance(chunk, AIMessageChunk):
                    continue

                # Check for reasoning_content (thinking)
                has_thinking = False
                if chunk.additional_kwargs:
                    reasoning = chunk.additional_kwargs.get("reasoning_content")
                    if reasoning:
                        has_thinking = True
                        yield ThinkingEvent(chunk=reasoning, session_id=session_id)

                # Stream content in real-time (only if not thinking)
                if not has_thinking and chunk.content:
                    content = chunk.content
                    if isinstance(content, str) and content.strip():
                        accumulated_content += content
                        yield ContentEvent(chunk=content, session_id=session_id)

                # Accumulate chunks so tool_call_chunks assemble into tool_calls
                accumulated_chunk = chunk if accumulated_chunk is None else (accumulated_chunk + chunk)

            # After the stream ends, check the assembled message for tool calls.
            # Using the accumulated message guarantees args are fully reconstructed
            # even when the provider streams JSON arguments across many chunks.
            if accumulated_chunk is not None and accumulated_chunk.tool_calls:
                from langchain_core.messages import ToolMessage

                tool_was_called = True
                tool_call_message = accumulated_chunk

                tool_messages: list[ToolMessage] = []
                for tool_call in accumulated_chunk.tool_calls:
                    if tool_call["name"] != "search_flights":
                        yield ErrorEvent(
                            error_code=ErrorCode.tool_error,
                            message=f"Unknown tool: {tool_call['name']}",
                            retryable=False,
                            tool_name=tool_call["name"],
                            raw_detail=None,
                            session_id=session_id,
                        )
                        return
                    if tool_call["name"] == "search_flights":
                        tool_start_time = time.time()
                        yield ToolCallEvent(
                            tool_name=tool_call["name"],
                            tool_args=tool_call["args"],
                            session_id=session_id,
                        )

                        self._metadata[session_id]["last_tool_invocation"] = {
                            "tool_name": tool_call["name"],
                            "tool_args": tool_call["args"],
                            "tool_call_id": tool_call.get("id", ""),
                        }

                        try:
                            tool_result = await search_flights.ainvoke(tool_call["args"])
                        except APIError as exc:
                            yield ErrorEvent(
                                error_code=ErrorCode.tool_error,
                                message=f"Tool {tool_call['name']} failed: {exc.message}",
                                retryable=exc.retryable,
                                tool_name=tool_call["name"],
                                raw_detail=_scrub(str(exc)),
                                session_id=session_id,
                            )
                            return
                        except Exception as exc:
                            yield ErrorEvent(
                                error_code=ErrorCode.tool_error,
                                message=f"Tool {tool_call['name']} failed.",
                                retryable=False,
                                tool_name=tool_call["name"],
                                raw_detail=_scrub(str(exc)),
                                session_id=session_id,
                            )
                            return

                        elapsed_ms = int((time.time() - tool_start_time) * 1000)
                        yield ToolResultEvent(
                            tool_name=tool_call["name"],
                            tool_result=str(tool_result),
                            elapsed_ms=elapsed_ms,
                            session_id=session_id,
                        )
                        tool_messages.append(
                            ToolMessage(
                                content=str(tool_result),
                                tool_call_id=tool_call.get("id", ""),
                            )
                        )

                tool_results = tool_messages

                messages_with_tools: list[BaseMessage] = [
                    *messages,
                    accumulated_chunk,
                    *tool_messages,
                ]

                accumulated_final = ""
                async for final_chunk in bound.astream(messages_with_tools):
                    if hasattr(final_chunk, "content") and isinstance(final_chunk.content, str) and final_chunk.content:
                        accumulated_final += final_chunk.content
                        yield ContentEvent(chunk=final_chunk.content, session_id=session_id)

                accumulated_content = accumulated_final
            stream_completed_cleanly = True
        finally:
            # Persist tool-call messages and the assistant response.
            # guard: only persist the AIMessage when the stream ran to completion
            # OR when accumulated_content has something worth saving. Early-return
            # error paths (unknown-tool, APIError, generic Exception) leave
            # accumulated_content="" and should not pollute history with blank
            # AIMessage entries that would be sent as context on subsequent turns.
            if tool_was_called and tool_call_message and tool_results:
                history.add_message(tool_call_message)
                for tool_msg in tool_results:
                    history.add_message(tool_msg)

            if stream_completed_cleanly or accumulated_content:
                history.add_ai_message(accumulated_content)
            elif tool_was_called and tool_results:
                # Post-tool LLM stream failed. Write a placeholder AIMessage so the
                # history ends with AIMessage → ToolMessage → AIMessage (valid
                # alternation). The retry endpoint can overwrite this on success.
                history.add_ai_message("")

        # Ensure at least one content event
        if not accumulated_content:
            yield ContentEvent(chunk="", session_id=session_id)
