"""Chat service using LangChain with tool calling.

Per Phase 4.5 Plan 06, ``ChatService`` no longer holds a singleton bound LLM.
Instead, it owns a per-app :class:`app.llm.factory.LLMProviderFactory` and a
``self._bound_providers`` dict keyed by ``session_id``. ``create_session`` is
``async`` because it absorbs the 4.2 provider-probe step (now per-provider via
:meth:`app.llm.protocol.LLMProvider.validate_config`) — the sequence is
``factory.build → validate_config → bind_tools → store``.

The 4.2 default fallbacks (``provider="ollama"``, ``model="qwen3:4b"``) live
in the route layer (``app.api.routes.routes.create_session``); the
:class:`app.llm.factory.SessionLLMConfig` dataclass requires both fields to be
non-``None`` at construction.
"""

import time
import uuid
from collections.abc import AsyncGenerator

from langchain_core.chat_history import InMemoryChatMessageHistory
from langchain_core.messages import AIMessage, HumanMessage

from app.llm.errors import ProbeError
from app.llm.factory import LLMProviderFactory, SessionLLMConfig
from app.llm.protocol import BoundProvider
from app.models import StreamEvent
from app.tools.flight_client import FlightAPIClient
from app.tools.flight_search import search_flights


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
        self._metadata: dict[str, dict[str, str]] = {}  # Session metadata (provider, model)
        self._bound_providers: dict[str, BoundProvider] = {}
        self._last_activity: dict[str, float] = {}

        # Wire the tool's client dependency here so callers don't need to know internals
        search_flights._flight_client = flight_client  # type: ignore[attr-defined]

    async def create_session(self, config: SessionLLMConfig) -> tuple[str, ProbeError | None]:
        """Create a new chat session: build provider, probe, bind tools, store.

        Args:
            config: Per-session LLM configuration (provider/model/base_url/api_key).

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
            "created_at": str(time.time()),
        }
        self._last_activity[session_id] = time.time()
        return session_id, None

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

    async def chat_stream(self, message: str, session_id: str) -> AsyncGenerator[StreamEvent]:
        """Stream a chat response chunk by chunk with tool calling support.

        Args:
            message: User message
            session_id: Session ID for conversation continuity

        Yields:
            StreamEvent objects with simplified structure
        """
        history = self.get_session_history(session_id)
        bound = self._bound_providers[session_id]

        # Build messages with history
        from langchain_core.messages import BaseMessage

        history_messages: list[BaseMessage] = list(history.messages)
        messages: list[BaseMessage] = [*history_messages, HumanMessage(content=message)]

        # Track state
        tool_was_called = False
        accumulated_content = ""
        tool_call_message = None
        tool_results = []

        # Stream LLM response
        async for chunk in bound.astream(messages):
            # Check for reasoning_content (thinking)
            has_thinking = False
            if hasattr(chunk, "additional_kwargs") and chunk.additional_kwargs:
                reasoning = chunk.additional_kwargs.get("reasoning_content")
                if reasoning:
                    has_thinking = True
                    yield StreamEvent(
                        chunk=reasoning,
                        session_id=session_id,
                        type="thinking",
                    )

            # Process content (only if not thinking)
            if not has_thinking and hasattr(chunk, "content") and chunk.content:
                content = chunk.content
                if isinstance(content, str) and content.strip():
                    accumulated_content += content
                    yield StreamEvent(
                        chunk=content,
                        session_id=session_id,
                        type="content",
                    )

            # Check for tool calls
            if isinstance(chunk, AIMessage) and chunk.tool_calls:
                tool_was_called = True
                tool_call_message = chunk

                from langchain_core.messages import ToolMessage

                tool_messages: list[ToolMessage] = []
                for tool_call in chunk.tool_calls:
                    if tool_call["name"] == "search_flights":
                        # Emit tool_call event
                        tool_start_time = time.time()
                        yield StreamEvent(
                            chunk="",
                            session_id=session_id,
                            type="tool_call",
                            tool_name=tool_call["name"],
                            tool_args=tool_call["args"],
                        )

                        # Execute the tool
                        tool_result = await search_flights.ainvoke(tool_call["args"])
                        tool_end_time = time.time()
                        elapsed_ms = int((tool_end_time - tool_start_time) * 1000)

                        # Emit tool_result event
                        yield StreamEvent(
                            chunk="",
                            session_id=session_id,
                            type="tool_result",
                            tool_name=tool_call["name"],
                            tool_result=str(tool_result),
                            elapsed_ms=elapsed_ms,
                        )

                        tool_messages.append(
                            ToolMessage(
                                content=str(tool_result),
                                tool_call_id=tool_call.get("id", ""),
                            )
                        )

                tool_results = tool_messages

                # Get final response after tool execution
                messages_with_tools: list[BaseMessage] = [
                    *messages,
                    chunk,
                    *tool_messages,
                ]

                # Stream the final response
                accumulated_final = ""
                async for final_chunk in bound.astream(messages_with_tools):
                    if hasattr(final_chunk, "content") and isinstance(final_chunk.content, str) and final_chunk.content:
                        accumulated_final += final_chunk.content
                        yield StreamEvent(
                            chunk=final_chunk.content,
                            session_id=session_id,
                            type="content",
                        )

                accumulated_content = accumulated_final
                break

        # Add messages to history
        history.add_user_message(message)

        if tool_was_called and tool_call_message and tool_results:
            history.add_message(tool_call_message)
            for tool_msg in tool_results:
                history.add_message(tool_msg)

        history.add_ai_message(accumulated_content)

        # Ensure at least one content event
        if not accumulated_content:
            yield StreamEvent(
                chunk="",
                session_id=session_id,
                type="content",
            )
