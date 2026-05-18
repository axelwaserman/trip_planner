"""Unit tests for :class:`app.llm.providers.openai.OpenAIProvider`.

Mirrors the assertion shape of
``backend/tests/unit/test_provider_probe.py::test_probe_cloud_missing_key``
(the 4.2 analog) — the cloud-provider missing-key case lifted onto the new
``OpenAIProvider.validate_config()`` member.

Per RESEARCH.md §"Pattern 4: validate_config for the Cloud Providers" the default
behavior is **key presence only** — no outbound API call. Live key validation
is opt-in via ``POST /api/providers/{provider}/test`` (Wave 3) and emits the
new ``ProbeErrorCode.INVALID_API_KEY`` value (which Plan 09 wires up).

API keys appear in fixtures only as the literal strings ``"sk-test"`` /
``"sk-bogus"`` — never a real key. Recorded in the Plan-04 threat register as
T-04.5-04-02 (disposition: mitigate).
"""


from app.llm.errors import ProbeErrorCode
from app.llm.providers.openai import OpenAIProvider


async def test_validate_config_returns_missing_api_key_when_key_is_none() -> None:
    """``OpenAIProvider(api_key=None).validate_config()`` → ``MISSING_API_KEY``."""
    # Arrange
    provider = OpenAIProvider(model="gpt-4o-mini", api_key=None)

    # Act
    result = await provider.validate_config()

    # Assert
    assert result is not None
    assert result.error == ProbeErrorCode.MISSING_API_KEY
    assert "OpenAI" in result.message
    # Hint mentions either the env-var or the new /settings/providers UI affordance.
    assert "OPENAI_API_KEY" in result.hint or "/settings/providers" in result.hint


async def test_validate_config_returns_missing_api_key_when_key_is_empty_string() -> None:
    """``OpenAIProvider(api_key="").validate_config()`` → ``MISSING_API_KEY``.

    Empty-string keys are treated identically to ``None`` per D-08 (truthy
    guard). Defense-in-depth: ``SessionCreateRequest`` already strips and
    normalises payload keys, but a literal empty string in a misconfigured
    ``.env`` file must not silently pass.
    """
    # Arrange
    provider = OpenAIProvider(model="gpt-4o-mini", api_key="")

    # Act
    result = await provider.validate_config()

    # Assert
    assert result is not None
    assert result.error == ProbeErrorCode.MISSING_API_KEY
    assert "OpenAI" in result.message


async def test_validate_config_returns_none_when_key_present() -> None:
    """``OpenAIProvider(api_key="sk-test").validate_config()`` → ``None``.

    Default validate_config is presence-only (D-13); does NOT make an outbound
    call. The literal ``"sk-test"`` is fine — never sent to api.openai.com.
    """
    # Arrange
    provider = OpenAIProvider(model="gpt-4o-mini", api_key="sk-test")

    # Act
    result = await provider.validate_config()

    # Assert
    assert result is None


async def test_list_models_returns_curated_openai_list() -> None:
    """``OpenAIProvider.list_models()`` returns the curated 5-element allow-list (D-04).

    Matches ``Settings.get_available_providers()["openai"]["models"]`` so the
    ``/api/llm/providers`` route and the provider class agree on the offered
    set. Curated, not live — cloud providers do not hit ``/v1/models`` on
    session-create in Phase 4.5.
    """
    # Arrange — list_models needs no key (curated, no HTTP).
    provider = OpenAIProvider(model="gpt-4o-mini", api_key=None)

    # Act
    result = await provider.list_models()

    # Assert
    assert result == ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "o1-mini", "o3-mini"]
