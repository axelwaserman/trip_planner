"""Wave 0 RED skeleton: gated live-Anthropic acceptance — extended-thinking events (D-13).

Per CONTEXT.md D-13, the Anthropic acceptance test proves the
``AnthropicProvider.build_agent`` rewrite wires end-to-end against the
real Anthropic endpoint and that extended-thinking-capable models emit
``ThinkingPart``-derived events when prompted to reason.

Gated on ``ANTHROPIC_API_KEY`` so default PR CI skips this test. Costs:
small handful of tokens per run.

The model name uses ``claude-3-7-sonnet-latest`` (extended-thinking
capable as of Phase 5 planning). If a future Anthropic model name changes,
the assertion still holds — Wave 2's ``AnthropicProvider`` is model-agnostic.

Analog: ``backend/tests/integration/test_cloud_providers_real.py`` —
function-level ``@pytest.mark.skipif`` gating pattern.
"""

import os

import pytest

pai = pytest.importorskip("pydantic_ai")
pytest.importorskip("pydantic_ai.messages")

deps_module = pytest.importorskip("app.chat.deps")
ChatDeps = deps_module.ChatDeps

from app.llm.providers.anthropic import AnthropicProvider
from app.tools.flight_client import MockFlightAPIClient

pytestmark = [
    pytest.mark.skipif(
        not os.getenv("ANTHROPIC_API_KEY"),
        reason="ANTHROPIC_API_KEY not set — skipping live Anthropic acceptance test.",
    ),
]


async def test_claude_emits_thinking_events_against_live_anthropic() -> None:
    """Live Anthropic → extended-thinking-capable Claude emits ThinkingPart events.

    Costs: a small handful of tokens per run against api.anthropic.com.
    Gated on ANTHROPIC_API_KEY so default PR CI skips this test.
    """
    from pydantic_ai.messages import (  # imported here so importorskip above gates module load
        PartDeltaEvent,
        PartStartEvent,
        ThinkingPart,
        ThinkingPartDelta,
    )

    provider = AnthropicProvider(
        model="claude-3-7-sonnet-latest",
        api_key=os.environ["ANTHROPIC_API_KEY"],
    )
    assert await provider.validate_config() is None

    deps = ChatDeps(
        flight_client=MockFlightAPIClient(seed=42),
        conversation_id="live-anthropic-test",
        user_id="ci",
    )
    agent = provider.build_agent(tools=[], deps_type=ChatDeps)
    saw_thinking = False
    async with agent.iter("Think briefly, then say 'pong'.", deps=deps) as agent_run:
        async for node in agent_run:
            stream_method = getattr(node, "stream", None)
            if stream_method is None:
                continue
            async with stream_method(agent_run.ctx) as stream:
                async for event in stream:
                    if (
                        isinstance(event, PartStartEvent)
                        and isinstance(event.part, ThinkingPart)
                        or isinstance(event, PartDeltaEvent)
                        and isinstance(event.delta, ThinkingPartDelta)
                    ):
                        saw_thinking = True
    assert saw_thinking, "claude-3-7-sonnet-latest must emit at least one ThinkingPart-derived event"
