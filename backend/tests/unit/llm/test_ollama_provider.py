"""Failing-stub tests for OllamaProvider (Phase 4.5 Wave 2 implements).

Mirrors ``backend/tests/unit/test_provider_probe.py`` (the 4.2 analog) — each
test stub here corresponds to one of the 4.2 ``probe_provider("ollama", ...)``
cases, lifted onto the new ``OllamaProvider.validate_config()`` member, plus
one new ``list_models`` test for the dynamic-discovery success criterion
(REQ-llm-provider-abstraction).

Wave 0 stub: every test body is ``pytest.skip("Wave 2 implements ...")``. The
test names + arrange shape are written in advance so Wave 2 can replace the
skip with a real assertion against ``app.llm.providers.ollama.OllamaProvider``
without renaming files or changing test discovery.

Per RESEARCH.md §"Pattern 1": ``OllamaProvider.bind_tools`` returns a runnable
that satisfies the ``BoundProvider`` Protocol; that surface is exercised by the
chat-stream integration tests in Wave 3, NOT here.

Future imports the real Wave-2 tests will need (deliberately omitted from this
stub file because ``app.llm.*`` does not exist yet)::

    from app.llm.errors import ProbeErrorCode
    from app.llm.providers.ollama import OllamaProvider
"""

import pytest

pytestmark = pytest.mark.unit


async def test_validate_config_returns_unreachable_on_connect_error() -> None:
    """ConnectError from ``httpx.AsyncClient.get`` → ``PROVIDER_UNREACHABLE``.

    Wave 2 mirrors test_provider_probe.test_probe_ollama_unreachable_on_connect_error::

        provider = OllamaProvider(
            model="qwen3:4b",
            base_url="http://localhost:11434",
            probe_timeout_seconds=1.0,
        )
        with patch("httpx.AsyncClient.get", new=AsyncMock(side_effect=httpx.ConnectError("refused"))):
            result = await provider.validate_config()
        assert result is not None
        assert result.error == ProbeErrorCode.PROVIDER_UNREACHABLE
    """
    pytest.skip("Wave 2 implements OllamaProvider")


async def test_validate_config_returns_unreachable_on_timeout() -> None:
    """``httpx.TimeoutException`` → ``PROVIDER_UNREACHABLE`` (mirrors test_probe_ollama_timeout)."""
    pytest.skip("Wave 2 implements OllamaProvider")


async def test_validate_config_returns_model_not_installed_when_tag_missing(
    mock_ollama_tags_response: object,
) -> None:
    """``/api/tags`` 200 but does not list the requested model → ``MODEL_NOT_INSTALLED``.

    Wave 2 uses the ``mock_ollama_tags_response`` factory fixture::

        response = mock_ollama_tags_response(["other:7b"])
        with patch("httpx.AsyncClient.get", new=AsyncMock(return_value=response)):
            result = await provider.validate_config()
        assert result.error == ProbeErrorCode.MODEL_NOT_INSTALLED
        assert "ollama pull qwen3:4b" in result.hint
    """
    pytest.skip("Wave 2 implements OllamaProvider")


async def test_validate_config_returns_none_when_model_present(
    mock_ollama_tags_response: object,
) -> None:
    """``/api/tags`` lists the requested model → ``validate_config`` returns ``None``."""
    pytest.skip("Wave 2 implements OllamaProvider")


async def test_list_models_returns_sorted_unique_ids_from_api_tags(
    mock_ollama_tags_response: object,
) -> None:
    """``OllamaProvider.list_models`` returns sorted, deduped model ids from ``/api/tags``.

    Covers the dynamic-discovery success criterion (REQ-llm-provider-abstraction §6).
    Per RESEARCH.md §"Pitfall 4" the implementation must defensively match on BOTH
    ``name`` and ``model`` keys to handle Ollama wire-shape drift.

    Wave 2 assertion shape::

        response = mock_ollama_tags_response(["qwen3:4b", "llama3:8b", "qwen3:4b"])
        with patch("httpx.AsyncClient.get", new=AsyncMock(return_value=response)):
            models = await provider.list_models()
        assert models == ["llama3:8b", "qwen3:4b"]  # sorted, deduped
    """
    pytest.skip("Wave 2 implements OllamaProvider")
