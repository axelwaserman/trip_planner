"""Wave 0 RED stub: OpenAIProvider o-series dispatch (D-14).

Per CONTEXT.md D-14 + RESEARCH §OpenAI Provider, the ``OpenAIProvider`` rewrite
in Wave 2 dispatches on the model name's prefix:

    "o1*" / "o3*"  → pydantic_ai.models.openai.OpenAIResponsesModel
    everything else → pydantic_ai.models.openai.OpenAIChatModel

The o-series prefixes live on ``Settings.openai_o_series_model_prefixes`` per
CLAUDE.md "tunables on Settings, not module constants".

Today, the imports below resolve via ``pytest.importorskip``:
- ``pydantic_ai.models.openai`` (Wave 4 dep swap)
- ``app.chat.deps`` (Wave 1)

The Phase 4.5 ``OpenAIProvider`` does not yet have ``build_agent``, so the
assertions below fail RED on a missing attribute until Wave 2 lands the
rewrite.

Analog: ``backend/tests/unit/llm/test_factory.py:27-55`` — the "match on
provider" dispatch test pattern.
"""

import pytest

pai_openai = pytest.importorskip("pydantic_ai.models.openai")
OpenAIChatModel = pai_openai.OpenAIChatModel
OpenAIResponsesModel = pai_openai.OpenAIResponsesModel

deps_module = pytest.importorskip("app.chat.deps")
ChatDeps = deps_module.ChatDeps

from app.llm.providers.openai import OpenAIProvider


def test_o3_mini_routes_to_openai_responses_model() -> None:
    """``o3-mini`` → OpenAIResponsesModel (D-14 o-series dispatch)."""
    provider = OpenAIProvider(model="o3-mini", api_key="sk-test")
    agent = provider.build_agent(tools=[], deps_type=ChatDeps)
    assert isinstance(agent.model, OpenAIResponsesModel)


def test_o1_mini_routes_to_openai_responses_model() -> None:
    """``o1-mini`` → OpenAIResponsesModel (D-14 o-series dispatch)."""
    provider = OpenAIProvider(model="o1-mini", api_key="sk-test")
    agent = provider.build_agent(tools=[], deps_type=ChatDeps)
    assert isinstance(agent.model, OpenAIResponsesModel)


def test_gpt_4o_mini_routes_to_openai_chat_model() -> None:
    """``gpt-4o-mini`` → OpenAIChatModel (the non-o-series default)."""
    provider = OpenAIProvider(model="gpt-4o-mini", api_key="sk-test")
    agent = provider.build_agent(tools=[], deps_type=ChatDeps)
    assert isinstance(agent.model, OpenAIChatModel)
