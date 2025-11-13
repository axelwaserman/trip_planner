"""LLM provider protocol and implementations."""

from collections.abc import AsyncGenerator
from typing import Any, Protocol, runtime_checkable

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage
from langchain_core.tools import BaseTool


@runtime_checkable
class LLMProvider(Protocol):
    """Protocol for LLM providers with tool calling support.
    
    This protocol defines the interface that all LLM providers must implement.
    It abstracts away the specific LLM backend (Ollama, OpenAI, Anthropic, etc.)
    and provides a consistent interface for the chat service.
    """

    async def ainvoke(self, messages: list[BaseMessage]) -> BaseMessage:
        """Invoke the LLM with a list of messages.
        
        Args:
            messages: List of messages to send to the LLM
            
        Returns:
            Response message from the LLM
        """
        ...

    def astream(self, messages: list[BaseMessage]) -> AsyncGenerator[BaseMessage, None]:
        """Stream LLM responses chunk by chunk.
        
        Args:
            messages: List of messages to send to the LLM
            
        Yields:
            Message chunks as they arrive from the LLM
        """
        ...

    def bind_tools(self, tools: list[BaseTool]) -> "LLMProvider":
        """Bind tools to the LLM for tool calling.
        
        Args:
            tools: List of LangChain tools to bind
            
        Returns:
            New provider instance with tools bound
        """
        ...

    @property
    def model_name(self) -> str:
        """Get the model name/identifier.
        
        Returns:
            Model name string
        """
        ...


class OllamaProvider:
    """Ollama LLM provider implementation.
    
    Wraps langchain_ollama.ChatOllama with the LLMProvider protocol.
    """

    def __init__(
        self,
        base_url: str,
        model: str,
        temperature: float = 0.7,
        reasoning: bool = True,
        **kwargs: Any,
    ) -> None:
        """Initialize Ollama provider.
        
        Args:
            base_url: Ollama server URL
            model: Model name (e.g., "qwen3:8b", "deepseek-r1:8b")
            temperature: Sampling temperature (0.0 to 1.0)
            reasoning: Enable thinking tokens for reasoning models
            **kwargs: Additional arguments passed to ChatOllama
        """
        from langchain_ollama import ChatOllama

        self._model_name = model
        self._llm: BaseChatModel = ChatOllama(
            base_url=base_url,
            model=model,
            temperature=temperature,
            reasoning=reasoning,
            **kwargs,
        )

    async def ainvoke(self, messages: list[BaseMessage]) -> BaseMessage:
        """Invoke the Ollama LLM.
        
        Args:
            messages: List of messages to send
            
        Returns:
            Response message from Ollama
        """
        return await self._llm.ainvoke(messages)

    def astream(self, messages: list[BaseMessage]) -> AsyncGenerator[BaseMessage, None]:
        """Stream Ollama responses.
        
        Args:
            messages: List of messages to send
            
        Yields:
            Message chunks from Ollama
        """
        return self._llm.astream(messages)

    def bind_tools(self, tools: list[BaseTool]) -> "OllamaProvider":
        """Bind tools to the Ollama LLM.
        
        Args:
            tools: List of LangChain tools
            
        Returns:
            New OllamaProvider instance with tools bound
        """
        # Create a new provider with tools bound to the underlying LLM
        new_provider = OllamaProvider.__new__(OllamaProvider)
        new_provider._model_name = self._model_name
        new_provider._llm = self._llm.bind_tools(tools)
        return new_provider

    @property
    def model_name(self) -> str:
        """Get the Ollama model name.
        
        Returns:
            Model name string
        """
        return self._model_name
