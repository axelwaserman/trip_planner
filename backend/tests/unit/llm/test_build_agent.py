"""Wave 0 RED stub: provider.build_agent(...) returns pydantic_ai.Agent (D-01..D-03).

Per CONTEXT.md D-01 + D-02 + RESEARCH.md §"Per-Provider Migration Rules", the
LangChain ``bind_tools`` → ``BoundProvider`` two-tier surface collapses into a
single ``build_agent(tools, deps_type) -> pydantic_ai.Agent`` method on each
concrete provider. PydanticAI's ``Agent`` IS the tool-bound thing.

The test file collects via ``pytest.importorskip`` for the not-yet-installed
``pydantic_ai`` package (added in Wave 4) AND the not-yet-existing
``app.chat.deps`` module (Wave 1).

Analog: ``backend/tests/unit/llm/test_ollama_provider.py:107-134`` — the
"per-provider unit test in AAA shape" pattern.
"""

import pytest

# pydantic-ai dep is added in Wave 4; importorskip lets collection succeed today.
pai = pytest.importorskip("pydantic_ai")
Agent = pai.Agent

# ChatDeps is created in Wave 1 (see test_deps.py for shape pinning).
deps_module = pytest.importorskip("app.chat.deps")
ChatDeps = deps_module.ChatDeps

from app.llm.providers.anthropic import AnthropicProvider
from app.llm.providers.lmstudio import LMStudioProvider
from app.llm.providers.ollama import OllamaProvider
from app.llm.providers.openai import OpenAIProvider
from app.tools.flight_search import search_flights


def test_ollama_provider_build_agent_returns_pydantic_ai_agent() -> None:
    """OllamaProvider.build_agent → pydantic_ai.Agent (no live network)."""
    provider = OllamaProvider(
        model="qwen3:4b",
        base_url="http://localhost:11434",
        probe_timeout_seconds=1.0,
    )
    agent = provider.build_agent(tools=[search_flights], deps_type=ChatDeps)
    assert isinstance(agent, Agent)


def test_ollama_build_agent_appends_v1_to_bare_host() -> None:
    """build_agent passes base_url + /v1 to PydanticAI's OllamaProvider.

    OllamaProvider._base_url is the bare host (scheme://host:port, no path).
    The frontend rejects any Ollama base_url that contains a path, so build_agent
    unconditionally appends /v1 without normalization logic.
    """
    from unittest.mock import patch

    provider = OllamaProvider(
        model="qwen3:4b",
        base_url="http://localhost:11434",
        probe_timeout_seconds=1.0,
    )

    captured: list[str] = []

    real_pai_provider = __import__("pydantic_ai.providers.ollama", fromlist=["OllamaProvider"]).OllamaProvider

    original_init = real_pai_provider.__init__

    def _capturing_init(self: object, *, base_url: str, **kwargs: object) -> None:
        captured.append(base_url)
        original_init(self, base_url=base_url, **kwargs)  # type: ignore[arg-type]

    with patch.object(real_pai_provider, "__init__", _capturing_init):
        provider.build_agent(tools=[], deps_type=ChatDeps)

    assert captured == ["http://localhost:11434/v1"]


def test_openai_provider_build_agent_returns_pydantic_ai_agent() -> None:
    """OpenAIProvider.build_agent → pydantic_ai.Agent (no live network)."""
    provider = OpenAIProvider(model="gpt-4o-mini", api_key="sk-test")
    agent = provider.build_agent(tools=[search_flights], deps_type=ChatDeps)
    assert isinstance(agent, Agent)


def test_anthropic_provider_build_agent_returns_pydantic_ai_agent() -> None:
    """AnthropicProvider.build_agent → pydantic_ai.Agent (no live network)."""
    provider = AnthropicProvider(
        model="claude-3-5-sonnet-20241022",
        api_key="sk-ant-test",
    )
    agent = provider.build_agent(tools=[search_flights], deps_type=ChatDeps)
    assert isinstance(agent, Agent)


def test_lmstudio_provider_build_agent_returns_pydantic_ai_agent() -> None:
    """LMStudioProvider.build_agent → pydantic_ai.Agent (no live network).

    Per RESEARCH §LM Studio Provider, ``OpenAIProvider(base_url=..., api_key=None)``
    auto-fills the ``"api-key-not-set"`` placeholder when ``OPENAI_API_KEY`` is
    unset, so the Phase 4.5 ``"lm-studio"`` sentinel retires.
    """
    provider = LMStudioProvider(
        model="local-model",
        base_url="http://localhost:1234/v1",
        probe_timeout_seconds=1.0,
    )
    agent = provider.build_agent(tools=[search_flights], deps_type=ChatDeps)
    assert isinstance(agent, Agent)
