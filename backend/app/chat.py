"""Chat service using LangChain and Ollama."""

import uuid
from collections.abc import AsyncGenerator

from langchain_core.chat_history import InMemoryChatMessageHistory
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.runnables.history import RunnableWithMessageHistory
from langchain_ollama import ChatOllama

from app.config import settings


class ChatService:
    """Service for managing chat conversations with LangChain."""

    def __init__(self) -> None:
        """Initialize the chat service."""
        self.llm = ChatOllama(
            base_url=settings.ollama_base_url,
            model=settings.ollama_model,
            temperature=0.7,
        )

        # Store chat histories by session_id
        self.store: dict[str, InMemoryChatMessageHistory] = {}

        # Create prompt template
        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "You are a helpful AI trip planning assistant. "
                    "Help users plan their trips by answering questions and providing recommendations.",
                ),
                MessagesPlaceholder(variable_name="history"),
                ("human", "{input}"),
            ]
        )

        # Create the chain with message history
        chain = prompt | self.llm
        self.chain_with_history = RunnableWithMessageHistory(
            chain,
            self._get_session_history,
            input_messages_key="input",
            history_messages_key="history",
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

        # Invoke the chain with history
        response = await self.chain_with_history.ainvoke(
            {"input": message},
            config={"configurable": {"session_id": session_id}},
        )

        # Extract text content from AIMessage
        response_text = response.content if hasattr(response, "content") else str(response)

        return response_text, session_id

    async def chat_stream(
        self, message: str, session_id: str | None = None
    ) -> AsyncGenerator[tuple[str, str]]:
        """Stream a chat response chunk by chunk.

        Args:
            message: User message
            session_id: Optional session ID for conversation continuity

        Yields:
            Tuples of (chunk, session_id) where chunk is a piece of the response
        """
        if session_id is None:
            session_id = str(uuid.uuid4())

        # Stream the chain with history
        async for chunk in self.chain_with_history.astream(
            {"input": message},
            config={"configurable": {"session_id": session_id}},
        ):
            # Extract text content from chunk
            content = chunk.content if hasattr(chunk, "content") else str(chunk)

            if content:
                yield content, session_id


# Global chat service instance
chat_service = ChatService()
