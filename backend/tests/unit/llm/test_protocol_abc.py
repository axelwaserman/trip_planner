"""Wave 0 RED stub: LLMProvider ABC conformance + BoundProvider absence (D-01..D-03).

Per CONTEXT.md D-01..D-03, the Phase 4.5 two-tier ``LLMProvider(Protocol)`` +
``BoundProvider(Protocol)`` shape collapses into a single ``LLMProvider(ABC)``
in Phase 5 — concrete providers explicitly subclass it (not duck-typed),
``BoundProvider`` retires entirely (PydanticAI's ``Agent`` IS the bound thing,
so the second tier is structurally redundant).

This file replaces ``test_protocol_conformance.py`` once Wave 1 deletes
``app/llm/protocol.py`` and creates ``app/llm/base.py``. Today the module
imports use ``pytest.importorskip("app.llm.base")`` so collection succeeds.

Anti-pattern lock: ``test_bound_provider_is_removed_from_module`` is the
explicit regression guard against re-introducing the two-tier shape (CONTEXT.md
"Don't ship a ProtocolProvider adapter alongside the new ABC").
"""

import inspect
import typing

import pytest

base_module = pytest.importorskip("app.llm.base")
LLMProvider = base_module.LLMProvider

# Concrete providers — these modules already exist (Phase 4.5) but Wave 1
# rewrites them to subclass the ABC explicitly (D-03). Today the imports
# resolve, but the ``issubclass(LLMProvider)`` assertions fail because the
# Phase 4.5 classes do NOT inherit from any ABC.
from app.llm.providers.anthropic import AnthropicProvider
from app.llm.providers.lmstudio import LMStudioProvider
from app.llm.providers.ollama import OllamaProvider
from app.llm.providers.openai import OpenAIProvider


def test_llm_provider_is_abc() -> None:
    """LLMProvider is an ``abc.ABC`` (CLAUDE.md "ABC, not Protocol")."""
    assert inspect.isabstract(LLMProvider) is True


def test_llm_provider_is_not_protocol() -> None:
    """LLMProvider is an ABC, never a typing.Protocol."""
    assert not isinstance(LLMProvider, type(typing.Protocol))


def test_ollama_provider_subclasses_llm_provider() -> None:
    """OllamaProvider explicitly subclasses LLMProvider (D-03)."""
    assert issubclass(OllamaProvider, LLMProvider)
    provider = OllamaProvider(model="qwen3:4b", base_url="http://x", probe_timeout_seconds=1.0)
    assert isinstance(provider, LLMProvider)


def test_openai_provider_subclasses_llm_provider() -> None:
    """OpenAIProvider explicitly subclasses LLMProvider (D-03)."""
    assert issubclass(OpenAIProvider, LLMProvider)
    provider = OpenAIProvider(model="gpt-4o-mini", api_key="sk-test")
    assert isinstance(provider, LLMProvider)


def test_anthropic_provider_subclasses_llm_provider() -> None:
    """AnthropicProvider explicitly subclasses LLMProvider (D-03)."""
    assert issubclass(AnthropicProvider, LLMProvider)
    provider = AnthropicProvider(model="claude-3-5-sonnet-20241022", api_key="sk-ant-test")
    assert isinstance(provider, LLMProvider)


def test_lmstudio_provider_subclasses_llm_provider() -> None:
    """LMStudioProvider explicitly subclasses LLMProvider (D-03)."""
    assert issubclass(LMStudioProvider, LLMProvider)


def test_bound_provider_is_removed_from_module() -> None:
    """Phase 5 retires BoundProvider entirely — no second tier (CONTEXT.md anti-pattern lock).

    Imports through ``app.llm.base`` (the new module name) MUST NOT expose
    a ``BoundProvider`` symbol. This is the regression guard against shipping
    a two-tier shape "just in case".
    """
    import app.llm.base

    assert not hasattr(app.llm.base, "BoundProvider")
