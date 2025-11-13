"""LLM provider factory."""

from typing import Any, Literal

from app.config import settings
from app.infrastructure.llm.provider import LLMProvider, OllamaProvider

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
    ) -> LLMProvider:
        """Create an LLM provider instance.
        
        Args:
            provider_type: Type of provider ("ollama", future: "openai", "anthropic")
            model: Model name override (uses config default if None)
            **kwargs: Additional provider-specific arguments
            
        Returns:
            LLMProvider instance
            
        Raises:
            ValueError: If provider_type is not supported
        """
        if provider_type == "ollama":
            return OllamaProvider(
                base_url=kwargs.get("base_url", settings.ollama_base_url),
                model=model or settings.ollama_model,
                temperature=kwargs.get("temperature", 0.7),
                reasoning=kwargs.get("reasoning", True),
            )
        else:
            raise ValueError(f"Unsupported provider type: {provider_type}")

    @staticmethod
    def get_default_provider() -> LLMProvider:
        """Get the default provider from config.
        
        Returns:
            Default LLMProvider instance
        """
        return LLMProviderFactory.create_provider(
            provider_type="ollama",
            model=settings.ollama_model,
        )
