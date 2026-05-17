"""Unit tests for :class:`app.llm.factory.LLMProviderFactory`.

Covers two concerns:

1. **Dispatch** — ``LLMProviderFactory.build(SessionLLMConfig(provider="ollama", ...))``
   returns an ``OllamaProvider`` instance, etc. Unknown provider names raise
   ``ValueError``. Per RESEARCH.md §"Pattern 2: Factory Builds from Session-Scoped
   Config", the implementation uses ``match config.provider`` against a fixed
   set of provider names.

2. **Key precedence (D-08)** — when a session payload provides ``api_key``, it
   wins over ``Settings.{provider}_api_key``. When the payload key is ``None``,
   the factory falls back to the env-var-derived ``Settings`` key. Same shape
   for ``base_url`` (Ollama).
"""

import pytest

from app.config import Settings
from app.llm.factory import LLMProviderFactory, SessionLLMConfig
from app.llm.providers.anthropic import AnthropicProvider
from app.llm.providers.ollama import OllamaProvider
from app.llm.providers.openai import OpenAIProvider

pytestmark = pytest.mark.unit


def test_factory_builds_ollama_provider_for_provider_name_ollama() -> None:
    """``factory.build(provider="ollama", ...)`` returns ``OllamaProvider``."""
    # Arrange
    settings = Settings()
    factory = LLMProviderFactory(settings)
    config = SessionLLMConfig(
        provider="ollama", model="qwen3:4b", base_url=None, api_key=None
    )

    # Act
    provider = factory.build(config)

    # Assert
    assert isinstance(provider, OllamaProvider)
    assert provider.get_provider_name() == "ollama"


def test_factory_builds_openai_provider_for_provider_name_openai() -> None:
    """``factory.build(provider="openai", ...)`` returns ``OpenAIProvider``."""
    # Arrange
    settings = Settings(openai_api_key="sk-test")
    factory = LLMProviderFactory(settings)
    config = SessionLLMConfig(
        provider="openai", model="gpt-4o-mini", base_url=None, api_key=None
    )

    # Act
    provider = factory.build(config)

    # Assert
    assert isinstance(provider, OpenAIProvider)
    assert provider.get_provider_name() == "openai"


def test_factory_builds_anthropic_provider_for_provider_name_anthropic() -> None:
    """``factory.build(provider="anthropic", ...)`` returns ``AnthropicProvider``."""
    # Arrange
    settings = Settings(anthropic_api_key="sk-ant-test")
    factory = LLMProviderFactory(settings)
    config = SessionLLMConfig(
        provider="anthropic",
        model="claude-3-5-sonnet-20241022",
        base_url=None,
        api_key=None,
    )

    # Act
    provider = factory.build(config)

    # Assert
    assert isinstance(provider, AnthropicProvider)
    assert provider.get_provider_name() == "anthropic"


def test_factory_uses_payload_api_key_over_settings_env_key() -> None:
    """D-08 precedence: payload ``api_key`` wins over ``Settings.openai_api_key``."""
    # Arrange
    settings = Settings(openai_api_key="sk-from-env")
    factory = LLMProviderFactory(settings)
    config = SessionLLMConfig(
        provider="openai",
        model="gpt-4o-mini",
        base_url=None,
        api_key="sk-from-payload",
    )

    # Act
    provider = factory.build(config)

    # Assert
    assert isinstance(provider, OpenAIProvider)
    assert provider._api_key == "sk-from-payload"


def test_factory_falls_back_to_settings_env_key_when_payload_key_is_none() -> None:
    """D-08 fallback: when payload ``api_key`` is ``None``, ``Settings`` key is used."""
    # Arrange
    settings = Settings(openai_api_key="sk-from-env")
    factory = LLMProviderFactory(settings)
    config = SessionLLMConfig(
        provider="openai", model="gpt-4o-mini", base_url=None, api_key=None
    )

    # Act
    provider = factory.build(config)

    # Assert
    assert isinstance(provider, OpenAIProvider)
    assert provider._api_key == "sk-from-env"


def test_factory_raises_value_error_for_unknown_provider() -> None:
    """Unknown provider name → ``ValueError`` (the ``match`` default branch)."""
    # Arrange
    settings = Settings()
    factory = LLMProviderFactory(settings)
    config = SessionLLMConfig(
        provider="bogus", model="x", base_url=None, api_key=None
    )

    # Act + Assert
    with pytest.raises(ValueError, match="Unknown provider"):
        factory.build(config)


def test_factory_uses_payload_base_url_over_settings_for_ollama() -> None:
    """D-08 precedence for base_url: payload value wins over ``Settings.ollama_base_url``."""
    # Arrange
    settings = Settings(ollama_base_url="http://settings-host:11434")
    factory = LLMProviderFactory(settings)
    config = SessionLLMConfig(
        provider="ollama",
        model="qwen3:4b",
        base_url="http://payload-host:11434",
        api_key=None,
    )

    # Act
    provider = factory.build(config)

    # Assert
    assert isinstance(provider, OllamaProvider)
    assert provider._base_url == "http://payload-host:11434"
