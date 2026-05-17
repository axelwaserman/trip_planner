"""Failing-stub tests for AnthropicProvider (Phase 4.5 Wave 2 implements).

Mirrors ``test_openai_provider.py`` — same shape, provider name ``anthropic``.

Per RESEARCH.md §"Pitfall 2: ChatAnthropic Requires a Non-Empty api_key at
Construction": ``ChatAnthropic.anthropic_api_key`` is required ``SecretStr`` (NOT
``Optional``). Constructing ``ChatAnthropic(api_key=None)`` raises a Pydantic
``ValidationError`` BEFORE any code path can probe it. Therefore
``AnthropicProvider.validate_config()`` MUST guard ``self._api_key is not None``
BEFORE constructing ``ChatAnthropic`` — and ``bind_tools`` must run AFTER
``validate_config`` (the factory ordering in ``chat.py::create_session`` already
guarantees this per Pattern 3).

Wave 0 stub: every test body is ``pytest.skip("Wave 2 implements ...")``.

Future imports the real Wave-2 tests will need::

    from app.llm.errors import ProbeErrorCode
    from app.llm.providers.anthropic import AnthropicProvider
"""

import pytest

pytestmark = pytest.mark.unit


async def test_validate_config_returns_missing_api_key_when_key_is_none() -> None:
    """``AnthropicProvider(api_key=None).validate_config()`` → ``MISSING_API_KEY``.

    Wave 2 assertion shape::

        provider = AnthropicProvider(model="claude-3-5-sonnet-20241022", api_key=None)
        result = await provider.validate_config()
        assert result is not None
        assert result.error == ProbeErrorCode.MISSING_API_KEY
        assert "Anthropic" in result.message
    """
    pytest.skip("Wave 2 implements AnthropicProvider")


async def test_validate_config_returns_missing_api_key_when_key_is_empty_string() -> None:
    """``AnthropicProvider(api_key="").validate_config()`` → ``MISSING_API_KEY`` (D-08 truthy guard)."""
    pytest.skip("Wave 2 implements AnthropicProvider")


async def test_validate_config_returns_none_when_key_present() -> None:
    """``AnthropicProvider(api_key="sk-ant-bogus").validate_config()`` → ``None``.

    Default validate_config is presence-only (D-13); does NOT construct
    ``ChatAnthropic`` (which would raise per Pitfall 2). The literal
    ``"sk-ant-bogus"`` is fine — never sent to api.anthropic.com.
    """
    pytest.skip("Wave 2 implements AnthropicProvider")
