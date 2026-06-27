"""Wave 0 RED skeleton: gated live-Ollama acceptance — qwen3 thinking events (D-13).

Per CONTEXT.md D-13, each provider must have a live acceptance test that
proves the thinking-token path works end-to-end against the real backend.
The test is gated on ``OLLAMA_BASE_URL`` being present in the environment;
default PR CI does not set it, so the test is skipped (not failed).

Today (Wave 0) the test is *additionally* skipped via a module-level
``pytest.skip`` until Wave 2 lands the ``OllamaProvider.build_agent``
rewrite. After Wave 2 + when ``OLLAMA_BASE_URL`` is set, the test runs
end-to-end and asserts that ``agent.iter`` emits at least one
``ThinkingPart``-derived event when the prompt asks the model to reason.

Analog: ``backend/tests/integration/test_cloud_providers_real.py`` —
function-level ``@pytest.mark.skipif`` gating pattern.
"""

import os

import pytest

# Wave 4 lands pydantic-ai; Wave 1 lands app.chat.deps; Wave 2 lands the
# rewritten OllamaProvider.build_agent. Until then, importorskip lets the
# file collect, and pytest.skip below keeps the test from running once
# imports happen to succeed in a partial-Wave state.
pai = pytest.importorskip("pydantic_ai")
pytest.importorskip("pydantic_ai.messages")

deps_module = pytest.importorskip("app.chat.deps")
ChatDeps = deps_module.ChatDeps

from app.llm.providers.ollama import OllamaProvider
from app.tools.flight_client import MockFlightAPIClient

pytestmark = [
    pytest.mark.skipif(
        not os.getenv("OLLAMA_BASE_URL"),
        reason="OLLAMA_BASE_URL not set — skipping live Ollama acceptance test.",
    ),
]


async def test_qwen3_emits_thinking_events_against_live_ollama() -> None:
    """Live Ollama → qwen3:4b emits at least one ThinkingPart-derived event.

    Costs: ~one inference round-trip against the configured Ollama daemon.
    Gated on OLLAMA_BASE_URL so default PR CI skips this test.
    """
    from pydantic_ai.messages import (  # imported here so importorskip above gates module load
        PartDeltaEvent,
        PartStartEvent,
        ThinkingPart,
        ThinkingPartDelta,
    )

    base_url = os.environ["OLLAMA_BASE_URL"]
    provider = OllamaProvider(model="qwen3:4b", base_url=base_url, probe_timeout_seconds=5.0)
    assert await provider.validate_config() is None

    deps = ChatDeps(
        flight_client=MockFlightAPIClient(seed=42),
        session_id="live-ollama-test",
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
    assert saw_thinking, "qwen3:4b must emit at least one ThinkingPart-derived event"
