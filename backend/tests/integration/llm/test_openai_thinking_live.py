"""Wave 0 RED skeleton: gated live-OpenAI acceptance — o-series thinking events (D-13).

Per CONTEXT.md D-13, the OpenAI o-series acceptance test proves the
``OpenAIResponsesModel`` dispatch (D-14) wires end-to-end against the
real OpenAI endpoint and that the o-series reasoning surface emits
``ThinkingPart``-derived events.

Gated on ``OPENAI_API_KEY`` so default PR CI skips this test. Costs:
~one inference round-trip against api.openai.com (o3-mini is the cheapest
o-series tier as of Phase 5 planning).

Analog: ``backend/tests/integration/test_cloud_providers_real.py`` —
function-level ``@pytest.mark.skipif`` gating pattern.
"""

import os

import pytest

pai = pytest.importorskip("pydantic_ai")
pytest.importorskip("pydantic_ai.messages")

deps_module = pytest.importorskip("app.chat.deps")
ChatDeps = deps_module.ChatDeps

from app.llm.providers.openai import OpenAIProvider
from app.tools.flight_client import MockFlightAPIClient

pytestmark = [
    pytest.mark.skipif(
        not os.getenv("OPENAI_API_KEY"),
        reason="OPENAI_API_KEY not set — skipping live OpenAI acceptance test.",
    ),
]


async def test_o3_mini_emits_thinking_events_against_live_openai() -> None:
    """Live OpenAI → o3-mini emits at least one ThinkingPart-derived event.

    Costs: ~one inference round-trip against api.openai.com using the cheapest
    o-series tier. Gated on OPENAI_API_KEY so default PR CI skips this test.
    """
    from pydantic_ai.messages import (  # imported here so importorskip above gates module load
        PartDeltaEvent,
        PartStartEvent,
        ThinkingPart,
        ThinkingPartDelta,
    )

    provider = OpenAIProvider(model="o3-mini", api_key=os.environ["OPENAI_API_KEY"])
    assert await provider.validate_config() is None

    deps = ChatDeps(
        flight_client=MockFlightAPIClient(seed=42),
        session_id="live-openai-test",
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
                    if isinstance(event, PartStartEvent) and isinstance(event.part, ThinkingPart):
                        saw_thinking = True
                    elif isinstance(event, PartDeltaEvent) and isinstance(
                        event.delta, ThinkingPartDelta
                    ):
                        saw_thinking = True
    assert saw_thinking, "o3-mini must emit at least one ThinkingPart-derived event"
