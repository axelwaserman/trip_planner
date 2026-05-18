"""Real-cloud acceptance tests for OpenAI and Anthropic providers (Phase 4.5).

These tests exercise a single live chat turn against the real cloud API to
prove the corresponding provider class wires end-to-end (key acceptance →
``bind_tools`` → ``ainvoke`` → response). They are GATED on the corresponding
``*_API_KEY`` env var being present in the test environment — when absent (the
default in PR CI), each test is **skipped**, never failed.

Per ROADMAP success criterion #6 — "Happy-path acceptance test exists for each
real cloud provider, gated on the corresponding API key being present in the
test environment (skipped in default PR CI)."

**Placement:** This file lives in ``backend/tests/integration/`` and NOT in
``backend/tests/e2e/``. Per ``backend/tests/e2e/README.md``:

    > What does NOT belong here:
    > - Tests that call a real LLM (Ollama, OpenAI, Anthropic, …). Chat-layer
    >   coverage lives in ``tests/integration/`` with mocks; Phase 4.4 introduces
    >   ``MockLLMStream`` for that.

Real-LLM acceptance tests are integration-level smoke tests against a real
external service; ``e2e/`` is reserved for full-stack auth-flow + travel-API
tests gated on a CI-available secret.

The gate uses **function-level** ``@pytest.mark.skipif`` decorators (NOT a
module-level skipif) so running with only ``OPENAI_API_KEY`` set still runs
the OpenAI test (and skips Anthropic), and vice versa. The
``pytest.mark.integration`` marker IS module-level — per
``backend/pyproject.toml`` ``[tool.pytest.ini_options].markers``.
"""

import os

import pytest
from langchain_core.messages import HumanMessage

from app.llm.providers.anthropic import AnthropicProvider
from app.llm.providers.openai import OpenAIProvider

pytestmark = pytest.mark.integration


@pytest.mark.skipif(
    not os.getenv("OPENAI_API_KEY"),
    reason="OPENAI_API_KEY not set — skipping real OpenAI cloud test.",
)
async def test_openai_provider_real_chat_turn() -> None:
    """End-to-end smoke test against api.openai.com.

    Gated on OPENAI_API_KEY. Costs ~1-3 tokens per run.
    """
    # Arrange
    provider = OpenAIProvider(model="gpt-4o-mini", api_key=os.environ["OPENAI_API_KEY"])
    assert await provider.validate_config() is None

    # Act
    bound = provider.bind_tools([])
    result = await bound.ainvoke(
        [HumanMessage(content="Reply with just the single word: pong")]
    )

    # Assert: tolerate punctuation; the model often returns "pong" or "pong."
    assert isinstance(result.content, str)
    assert "pong" in result.content.lower()


@pytest.mark.skipif(
    not os.getenv("ANTHROPIC_API_KEY"),
    reason="ANTHROPIC_API_KEY not set — skipping real Anthropic cloud test.",
)
async def test_anthropic_provider_real_chat_turn() -> None:
    """End-to-end smoke test against api.anthropic.com.

    Gated on ANTHROPIC_API_KEY. Costs a small handful of tokens per run; uses
    claude-3-5-haiku for the cheapest tier.

    ``langchain_anthropic 1.4.3`` returns ``AIMessage.content`` as a list of
    content blocks for some configurations; coerce via ``str(...)`` for a
    tolerant assertion against either shape.
    """
    # Arrange
    provider = AnthropicProvider(
        model="claude-3-5-haiku-20241022",
        api_key=os.environ["ANTHROPIC_API_KEY"],
    )
    assert await provider.validate_config() is None

    # Act
    bound = provider.bind_tools([])
    result = await bound.ainvoke(
        [HumanMessage(content="Reply with just the single word: pong")]
    )

    # Assert: tolerant of str-or-list content shape per langchain_anthropic 1.4.3
    assert "pong" in str(result.content).lower()
