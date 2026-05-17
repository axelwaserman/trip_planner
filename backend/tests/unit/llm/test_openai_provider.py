"""Failing-stub tests for OpenAIProvider (Phase 4.5 Wave 2 implements).

Mirrors ``backend/tests/unit/test_provider_probe.py::test_probe_cloud_missing_key``
(the 4.2 analog) — the cloud-provider missing-key case lifted onto the new
``OpenAIProvider.validate_config()`` member.

Per RESEARCH.md §"Pattern 4: validate_config for the Cloud Providers" the default
behavior is **key presence only** — no outbound API call. Live key validation is
opt-in via ``POST /api/providers/{provider}/test`` (Wave 3) and emits the new
``ProbeErrorCode.INVALID_API_KEY`` value.

Wave 0 stub: every test body is ``pytest.skip("Wave 2 implements ...")``.

API keys appear in test fixtures only as the literal string ``"sk-bogus"`` — never
a real key. This is recorded in the threat register (T-04.5-01-02 disposition: accept).

Future imports the real Wave-2 tests will need::

    from app.llm.errors import ProbeErrorCode
    from app.llm.providers.openai import OpenAIProvider
"""

import pytest

pytestmark = pytest.mark.unit


async def test_validate_config_returns_missing_api_key_when_key_is_none() -> None:
    """``OpenAIProvider(api_key=None).validate_config()`` → ``MISSING_API_KEY``.

    Wave 2 assertion shape::

        provider = OpenAIProvider(model="gpt-4o-mini", api_key=None)
        result = await provider.validate_config()
        assert result is not None
        assert result.error == ProbeErrorCode.MISSING_API_KEY
        assert "OpenAI" in result.message
    """
    pytest.skip("Wave 2 implements OpenAIProvider")


async def test_validate_config_returns_missing_api_key_when_key_is_empty_string() -> None:
    """``OpenAIProvider(api_key="").validate_config()`` → ``MISSING_API_KEY``.

    Empty-string keys are treated identically to ``None`` per D-08 (truthy guard).
    """
    pytest.skip("Wave 2 implements OpenAIProvider")


async def test_validate_config_returns_none_when_key_present() -> None:
    """``OpenAIProvider(api_key="sk-bogus").validate_config()`` → ``None``.

    Default validate_config is presence-only (D-13); does NOT make an outbound
    call. The literal ``"sk-bogus"`` is fine — never sent to api.openai.com.
    """
    pytest.skip("Wave 2 implements OpenAIProvider")
