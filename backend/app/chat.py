"""Chat service using LangChain with tool calling."""

import time
import uuid
from collections.abc import AsyncGenerator

from langchain_core.chat_history import InMemoryChatMessageHistory
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage

from app.models import StreamEvent
from app.tools.flight_client import FlightAPIClient
from app.tools.flight_search import search_flights


class ChatService:
    """Service for managing chat conversations with LangChain and tool calling."""

    def __init__(self, flight_client: FlightAPIClient, llm: BaseChatModel) -> None:
        """Initialize the chat service with flight client and LLM.

        Args:
            flight_client: Flight API client for tool to use
            llm: LangChain BaseChatModel instance (ChatOllama, ChatOpenAI, etc.)
        """
        self._histories: dict[str, InMemoryChatMessageHistory] = {}
        self._metadata: dict[str, dict[str, str]] = {}  # Session metadata (provider, model)
        self._last_activity: dict[str, float] = {}

        # Inject flight client into the tool
        search_flights._flight_client = flight_client

        # Bind tools to LLM
        self.llm = llm.bind_tools([search_flights])

    def create_session(
        self,
        provider: str | None = None,
        model: str | None = None
    ) -> str:
        """Create a new chat session with optional provider/model selection.

        Args:
            provider: LLM provider name (ollama, openai, anthropic)
            model: Model name for the provider

        Returns:
            New session ID (UUID)
        """
        session_id = str(uuid.uuid4())
        self._histories[session_id] = InMemoryChatMessageHistory()
        self._metadata[session_id] = {
            "provider": provider or "ollama",
            "model": model or "qwen3:4b",
            "created_at": str(time.time()),
        }
        self._last_activity[session_id] = time.time()
        return session_id

    def get_session_history(self, session_id: str) -> InMemoryChatMessageHistory | None:
        """Get history for a session.

        Args:
            session_id: Session identifier

        Returns:
            Chat history if session exists, None otherwise
        """
        if session_id in self._histories:
            self._last_activity[session_id] = time.time()
            return self._histories[session_id]
        return None

    def cleanup_expired_sessions(self, max_age_seconds: int = 3600) -> int:
        """Remove expired sessions based on inactivity.

        Args:
            max_age_seconds: Maximum age since last activity (default: 1 hour)

        Returns:
            Number of sessions cleaned up
        """
        now = time.time()
        expired = [
            sid
            for sid, last_active in self._last_activity.items()
            if now - last_active > max_age_seconds
        ]

        for session_id in expired:
            self._histories.pop(session_id, None)
            self._metadata.pop(session_id, None)
            self._last_activity.pop(session_id, None)

        return len(expired)

    async def chat_stream(
        self, message: str, session_id: str
    ) -> AsyncGenerator[StreamEvent]:
        """Stream a chat response chunk by chunk with tool calling support.

        Args:
            message: User message
            session_id: Session ID for conversation continuity

        Yields:
            StreamEvent objects with simplified structure
        """
        history = self.get_session_history(session_id)
        if not history:
            yield StreamEvent(
                chunk="",
                session_id=session_id,
                type="content",
            )
            return

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
        async for chunk in self.llm.astream(messages):
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
                if content.strip():
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
                async for final_chunk in self.llm.astream(messages_with_tools):
                    if hasattr(final_chunk, "content") and final_chunk.content:
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
