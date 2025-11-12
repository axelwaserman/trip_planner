"""Chat service using LangChain with tool calling via bind_tools()."""

import uuid
from collections.abc import AsyncGenerator

from langchain_core.chat_history import InMemoryChatMessageHistory
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.tools import tool
from langchain_ollama import ChatOllama

from app.config import settings
from app.services.flight import FlightService
from app.tools.flight_search import create_flight_search_tool


class ChatService:
    """Service for managing chat conversations with LangChain and tool calling."""

    def __init__(self, flight_service: FlightService) -> None:
        """Initialize the chat service with tools.

        Args:
            flight_service: FlightService instance for flight search tool
        """
        # Store chat histories by session_id
        self.store: dict[str, InMemoryChatMessageHistory] = {}

        # Create flight search tool function
        flight_search_func = create_flight_search_tool(flight_service)

        # Convert to LangChain tool decorator format
        self.search_flights_tool = tool(flight_search_func)

        # Create LLM with tools bound (correct API per LangChain docs)
        self.llm = ChatOllama(
            base_url=settings.ollama_base_url,
            model=settings.ollama_model,
            temperature=0.7,
        ).bind_tools([self.search_flights_tool])

    def _get_session_history(self, session_id: str) -> InMemoryChatMessageHistory:
        """Get or create chat history for a session.

        Args:
            session_id: Session identifier

        Returns:
            Chat message history for the session
        """
        if session_id not in self.store:
            self.store[session_id] = InMemoryChatMessageHistory()
        return self.store[session_id]

    async def chat(self, message: str, session_id: str | None = None) -> tuple[str, str]:
        """Send a message and get a response with tool calling support.

        Args:
            message: User message
            session_id: Optional session ID for conversation continuity

        Returns:
            Tuple of (response, session_id)
        """
        if session_id is None:
            session_id = str(uuid.uuid4())

        # Get chat history
        history = self._get_session_history(session_id)

        # Build messages with history
        from langchain_core.messages import BaseMessage
        
        history_messages: list[BaseMessage] = list(history.messages)
        messages: list[BaseMessage] = [*history_messages, HumanMessage(content=message)]

        # Invoke LLM (may return tool calls)
        result = await self.llm.ainvoke(messages)

        # Check if LLM wants to call tools
        response_text: str
        if isinstance(result, AIMessage) and result.tool_calls:
            # Execute tool calls
            from langchain_core.messages import ToolMessage
            
            tool_messages: list[ToolMessage] = []
            for tool_call in result.tool_calls:
                if tool_call["name"] == "search_flights":
                    # Execute the tool
                    tool_result = await self.search_flights_tool.ainvoke(tool_call["args"])
                    tool_messages.append(
                        ToolMessage(
                            content=str(tool_result),
                            tool_call_id=tool_call.get("id", ""),
                        )
                    )

            # Get final response after tool execution
            messages_with_tools: list[BaseMessage] = [
                *messages,
                result,  # AI message with tool calls
                *tool_messages,  # Tool results
            ]
            final_result = await self.llm.ainvoke(messages_with_tools)
            response_text = str(final_result.content) if hasattr(final_result, "content") else str(final_result)
        else:
            # No tool calls, use response directly
            response_text = str(result.content) if hasattr(result, "content") else str(result)

        # Add messages to history
        history.add_user_message(message)
        history.add_ai_message(response_text)

        return response_text, session_id

    async def chat_stream(
        self, message: str, session_id: str | None = None
    ) -> AsyncGenerator[tuple[str, str]]:
        """Stream a chat response chunk by chunk.

        Note: Streaming with tool calls is complex. This will be implemented
        in Checkpoint 5. For now, returns non-streaming response.

        Args:
            message: User message
            session_id: Optional session ID for conversation continuity

        Yields:
            Tuples of (chunk, session_id) where chunk is a piece of the response
        """
        # Non-streaming fallback for now - invoke and yield complete response
        response_text, final_session_id = await self.chat(message, session_id)
        yield response_text, final_session_id


def create_chat_service(flight_service: FlightService) -> ChatService:
    """Factory function to create ChatService with dependencies.

    Args:
        flight_service: FlightService instance for tools

    Returns:
        Configured ChatService instance
    """
    return ChatService(flight_service=flight_service)
