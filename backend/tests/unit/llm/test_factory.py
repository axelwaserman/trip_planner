"""Failing-stub tests for LLMProviderFactory (Phase 4.5 Wave 3 implements).

Covers two concerns:

1. **Dispatch** — ``LLMProviderFactory.build(SessionLLMConfig(provider="ollama", ...))``
   returns an ``OllamaProvider`` instance, etc. Unknown provider names raise
   ``ValueError``. Per RESEARCH.md §"Pattern 2: Factory Builds from Session-Scoped
   Config", the implementation uses ``match config.provider`` against a fixed
   set of provider names.

2. **Key precedence (D-08)** — when a session payload provides ``api_key``, it
   wins over ``Settings.{provider}_api_key``. When the payload key is ``None``,
   the factory falls back to the env-var-derived ``Settings`` key. This is the
   D-08 contract documented in RESEARCH.md §"User Constraints — API Keys".

Wave 0 stub: every test body is ``pytest.skip("Wave 3 implements ...")``.

Future imports the real Wave-3 tests will need::

    from app.config import Settings
    from app.llm.factory import LLMProviderFactory, SessionLLMConfig
    from app.llm.providers.ollama import OllamaProvider
    from app.llm.providers.openai import OpenAIProvider
    from app.llm.providers.anthropic import AnthropicProvider
"""

import pytest

pytestmark = pytest.mark.unit


def test_factory_builds_ollama_provider_for_provider_name_ollama() -> None:
    """``factory.build(provider="ollama", ...)`` returns ``OllamaProvider``.

    Wave 3 assertion shape::

        settings = Settings()
        factory = LLMProviderFactory(settings)
        config = SessionLLMConfig(
            provider="ollama", model="qwen3:4b", base_url=None, api_key=None,
        )
        provider = factory.build(config)
        assert isinstance(provider, OllamaProvider)
        assert provider.get_provider_name() == "ollama"
    """
    pytest.skip("Wave 3 implements LLMProviderFactory")


def test_factory_builds_openai_provider_for_provider_name_openai() -> None:
    """``factory.build(provider="openai", ...)`` returns ``OpenAIProvider``."""
    pytest.skip("Wave 3 implements LLMProviderFactory")


def test_factory_builds_anthropic_provider_for_provider_name_anthropic() -> None:
    """``factory.build(provider="anthropic", ...)`` returns ``AnthropicProvider``."""
    pytest.skip("Wave 3 implements LLMProviderFactory")


def test_factory_uses_payload_api_key_over_settings_env_key() -> None:
    """D-08 precedence: payload ``api_key`` wins over ``Settings.openai_api_key``.

    Wave 3 assertion shape (key inspection via private attribute or behaviour)::

        settings = Settings(openai_api_key="sk-from-env")
        factory = LLMProviderFactory(settings)
        config = SessionLLMConfig(
            provider="openai", model="gpt-4o-mini",
            base_url=None, api_key="sk-from-payload",
        )
        provider = factory.build(config)
        assert provider._api_key == "sk-from-payload"  # NOT "sk-from-env"
    """
    pytest.skip("Wave 3 implements LLMProviderFactory")


def test_factory_falls_back_to_settings_env_key_when_payload_key_is_none() -> None:
    """D-08 fallback: when payload ``api_key`` is ``None``, ``Settings`` key is used.

    Wave 3 assertion shape::

        settings = Settings(openai_api_key="sk-from-env")
        factory = LLMProviderFactory(settings)
        config = SessionLLMConfig(
            provider="openai", model="gpt-4o-mini", base_url=None, api_key=None,
        )
        provider = factory.build(config)
        assert provider._api_key == "sk-from-env"
    """
    pytest.skip("Wave 3 implements LLMProviderFactory")


def test_factory_raises_value_error_for_unknown_provider() -> None:
    """Unknown provider name → ``ValueError`` (the ``match`` default branch).

    Wave 3 assertion shape::

        config = SessionLLMConfig(
            provider="bogus", model="x", base_url=None, api_key=None,
        )
        with pytest.raises(ValueError, match="Unknown provider"):
            factory.build(config)
    """
    pytest.skip("Wave 3 implements LLMProviderFactory")
