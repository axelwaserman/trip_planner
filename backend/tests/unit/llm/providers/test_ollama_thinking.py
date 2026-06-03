"""Wave 0 RED stub: qwen3 ``<think>`` thinking-tag surface via PydanticAI ModelProfile.

Per CONTEXT.md D-12 and RESEARCH OQ-04, PydanticAI's ``OllamaProvider``
inherits ``thinking_tags=('<think>', '</think>')`` from
``pydantic_ai.profiles.qwen.qwen_model_profile``, which is what makes qwen3's
native ``<think>`` reasoning tokens parse into ``ThinkingPart`` events
without needing any explicit ``reasoning=True`` flag.

The Phase 4.5 ``_model_supports_reasoning`` prefix gating retires (D-12) —
the prefix list moves from ``Settings.ollama_reasoning_model_prefixes``
into PydanticAI's ``ModelProfile`` (out of repo control), so the Wave 0
test pins the contract that the inherited profile is the right one for qwen3.

The exact attribute path on ``agent.model`` differs across PydanticAI 0.8.1
versions (private ``_model_profile`` vs public ``profile``); the test reads
whichever is present.
"""

import pytest

pai = pytest.importorskip("pydantic_ai")
pytest.importorskip("pydantic_ai.models.openai")
pytest.importorskip("pydantic_ai.providers.ollama")

deps_module = pytest.importorskip("app.chat.deps")
ChatDeps = deps_module.ChatDeps

from app.llm.providers.ollama import OllamaProvider


def test_qwen3_model_profile_includes_default_thinking_tags() -> None:
    """qwen3 builds an ``Agent`` whose model profile carries ``<think>`` thinking tags.

    PydanticAI's ``OllamaProvider`` inherits ``qwen_model_profile``, which sets
    ``thinking_tags=('<think>', '</think>')``. The Phase 5 OllamaProvider
    rewrite must NOT override this — qwen3's reasoning tokens then parse
    natively into ``ThinkingPart`` deltas.
    """
    provider = OllamaProvider(
        model="qwen3:4b",
        base_url="http://localhost:11434",
        probe_timeout_seconds=1.0,
    )
    agent = provider.build_agent(tools=[], deps_type=ChatDeps)

    # Read whichever attribute PydanticAI 0.8.1 exposes — public ``profile``
    # is the documented surface; ``_model_profile`` is the private fallback.
    profile = getattr(agent.model, "profile", None) or getattr(
        agent.model, "_model_profile", None
    )
    assert profile is not None, "agent.model must expose a model profile"
    assert profile.thinking_tags == ("<think>", "</think>")
