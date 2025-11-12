"""Chat service using LangChain agent with tools."""

import uuid
from collections.abc import AsyncGenerator

from langchain.agents import create_agent
from langchain_core.chat_history import InMemoryChatMessageHistory
from langchain_core.tools import StructuredTool
from langchain_ollama import ChatOllama

from app.config import settings
from app.services.flight import FlightService
from app.tools.flight_search import create_flight_search_tool


class ChatService:
    """Service for managing chat conversations with LangChain agent."""

    def __init__(self, flight_service: FlightService) -> None:
        """Initialize the chat service with tools.

        Args:
            flight_service: FlightService instance for flight search tool
        """
        self.llm = ChatOllama(
            base_url=settings.ollama_base_url,
            model=settings.ollama_model,
            temperature=0.7,
        )

        # Store chat histories by session_id
        self.store: dict[str, InMemoryChatMessageHistory] = {}

        # Create tools with closure over services
        flight_search_func = create_flight_search_tool(flight_service)
        tools = [
            StructuredTool.from_function(
                coroutine=flight_search_func,
                name="search_flights",
                description=flight_search_func.__doc__ or "Search for flights",
            )
        ]

        # Create ReAct agent using LangGraph
        # Note: Using langchain.agents.create_agent (LangChain 1.0 API)
        # which wraps LangGraph's create_react_agent
        self.agent_executor = create_agent(
            model=self.llm,
            tools=tools,
            system_prompt=(
                "You are a helpful AI trip planning assistant. "
                "Help users plan their trips by searching for flights, answering questions, "
                "and providing recommendations. Use the available tools when needed to help users."
            ),
        )

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
        """Send a message and get a response.

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

        # Invoke agent with message and history
        result = await self.agent_executor.ainvoke(
            {"messages": [*history.messages, ("user", message)]}
        )

        # Extract response from agent output
        # LangGraph agent returns dict with 'messages' key containing message list
        messages = result.get("messages", [])
        if messages:
            last_message = messages[-1]
            response_text = (
                last_message.content
                if hasattr(last_message, "content")
                else str(last_message)
            )
        else:
            response_text = "I'm sorry, I couldn't generate a response."

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
