"""LLM provider factory."""

from typing import Any, Literal

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_ollama import ChatOllama

from app.config import settings

ProviderType = Literal["ollama"]


class LLMProviderFactory:
    """Factory for creating LLM provider instances.
    
    Supports multiple LLM backends with consistent interface.
    """

    @staticmethod
    def create_provider(
        provider_type: ProviderType = "ollama",
        model: str | None = None,
        **kwargs: Any,
    ) -> BaseChatModel:
        """Create an LLM provider instance.
        
        Args:
            provider_type: Type of provider ("ollama", future: "openai", "anthropic")
            model: Model name override (uses config default if None)
            **kwargs: Additional provider-specific arguments
            
        Returns:
            BaseChatModel instance (ChatOllama, or future: ChatOpenAI, ChatAnthropic)
            
        Raises:
            ValueError: If provider_type is not supported
        """
        if provider_type == "ollama":
            return ChatOllama(
                base_url=kwargs.get("base_url", settings.ollama_base_url),
                model=model or settings.ollama_model,
                temperature=kwargs.get("temperature", 0.7),
                reasoning=kwargs.get("reasoning", True),
            )
        else:
            raise ValueError(f"Unsupported provider type: {provider_type}")

    @staticmethod
    def get_default_provider() -> BaseChatModel:
        """Get the default provider from config.
        
        Returns:
            Default BaseChatModel instance
        """
        return LLMProviderFactory.create_provider(
            provider_type="ollama",
            model=settings.ollama_model,
        )
