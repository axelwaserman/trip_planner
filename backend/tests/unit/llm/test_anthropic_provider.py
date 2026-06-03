"""Unit tests for :class:`app.llm.providers.anthropic.AnthropicProvider` (Wave 2 — Plan 04.5-05).

Mirrors :mod:`backend.tests.unit.llm.test_openai_provider` — the cloud-provider
shape lifted onto Anthropic. The four ``validate_config`` / ``list_models``
tests exercise the same key-presence-only contract from
:mod:`backend.tests.unit.test_provider_probe.test_probe_cloud_missing_key` (the
4.2 analog) plus an Anthropic-specific regression for **Pitfall 2** (RESEARCH.md):

    ``ChatAnthropic.anthropic_api_key`` is a required Pydantic ``SecretStr``;
    constructing ``ChatAnthropic(api_key=None)`` raises a Pydantic
    ``ValidationError`` BEFORE any user code can intercept it. Therefore
    :meth:`AnthropicProvider.bind_tools` carries an ``assert self._api_key is
    not None`` precondition guard, converting that misuse into a clean
    :class:`AssertionError` rather than a leaky validation stack trace. The
    last test pins this behaviour.

Default ``validate_config`` is presence-only (D-13); no outbound API call is
made. The literal API-key strings here (``"sk-ant-bogus"``, ``"sk-ant-test"``)
are never sent to ``api.anthropic.com`` — recorded in the threat register
(T-04.5-05-01 disposition: mitigate).
"""

import pytest

from app.llm.errors import ProbeErrorCode
from app.llm.providers.anthropic import AnthropicProvider


async def test_validate_config_returns_missing_api_key_when_key_is_none() -> None:
    """``AnthropicProvider(api_key=None).validate_config()`` → ``MISSING_API_KEY``."""
    # Arrange
    provider = AnthropicProvider(model="claude-3-5-sonnet-20241022", api_key=None)

    # Act
    result = await provider.validate_config()

    # Assert
    assert result is not None
    assert result.error == ProbeErrorCode.MISSING_API_KEY
    assert "Anthropic" in result.message
    assert "ANTHROPIC_API_KEY" in result.hint or "/settings/providers" in result.hint


async def test_validate_config_returns_missing_api_key_when_key_is_empty_string() -> None:
    """``AnthropicProvider(api_key="").validate_config()`` → ``MISSING_API_KEY`` (D-08 truthy guard)."""
    # Arrange
    provider = AnthropicProvider(model="claude-3-5-sonnet-20241022", api_key="")

    # Act
    result = await provider.validate_config()

    # Assert
    assert result is not None
    assert result.error == ProbeErrorCode.MISSING_API_KEY
    assert "Anthropic" in result.message
    assert "ANTHROPIC_API_KEY" in result.hint or "/settings/providers" in result.hint


async def test_validate_config_returns_none_when_key_present() -> None:
    """``AnthropicProvider(api_key="sk-ant-bogus").validate_config()`` → ``None``.

    Default ``validate_config`` is presence-only (D-13); does NOT construct
    ``ChatAnthropic`` (which would raise per Pitfall 2 if the key were ``None``).
    The literal ``"sk-ant-bogus"`` is fine — never sent to ``api.anthropic.com``.
    """
    # Arrange
    provider = AnthropicProvider(model="claude-3-5-sonnet-20241022", api_key="sk-ant-bogus")

    # Act
    result = await provider.validate_config()

    # Assert
    assert result is None


async def test_list_models_returns_curated_anthropic_list() -> None:
    """``AnthropicProvider.list_models()`` returns the curated D-04 list verbatim.

    The list MUST stay in sync with
    ``Settings.get_available_providers()["anthropic"]["models"]``.
    """
    # Arrange
    provider = AnthropicProvider(model="claude-3-5-sonnet-20241022", api_key="sk-ant-bogus")

    # Act
    result = await provider.list_models()

    # Assert
    assert result == [
        "claude-3-5-sonnet-20241022",
        "claude-3-5-haiku-20241022",
        "claude-3-opus-20240229",
    ]


def test_build_agent_raises_assertion_error_when_validate_config_was_skipped() -> None:
    """Pitfall 4 regression: ``build_agent`` MUST refuse to construct
    ``AnthropicProvider`` when ``api_key`` is ``None``, raising
    :class:`AssertionError` before the SDK can raise its own
    ``pydantic_ai.UserError`` (whose message could include field-path detail
    in logs). This pins the precondition guard in
    :meth:`AnthropicProvider.build_agent` — protecting against a direct caller
    who skips :meth:`validate_config` (the normal flow goes through the factory
    + ``ChatService.create_session`` ordering).

    Phase 5 / Plan 05-03 rewrites the Pitfall 2 (Phase 4.5 ``bind_tools``)
    regression onto Pitfall 4 (Phase 5 ``build_agent``); the underlying
    invariant is unchanged, only the SDK + method-name moved.
    """
    # Arrange
    provider = AnthropicProvider(model="claude-3-5-sonnet-20241022", api_key=None)

    # Act + Assert
    with pytest.raises(AssertionError):
        provider.build_agent(tools=[], deps_type=object)
