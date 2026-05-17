"""Protocol conformance tests for the LLMProvider abstraction (Phase 4.5).

When Wave 1 lands ``app/llm/protocol.py`` defining the ``LLMProvider`` and
``BoundProvider`` ``Protocol``s, AND Wave 2 lands the four concrete provider
classes (Ollama / LM Studio / OpenAI / Anthropic), this test asserts that each
class structurally satisfies the runtime-checkable Protocol.

Per RESEARCH.md §"Pattern 1: Two-Protocol Shape" the contract is:

    @runtime_checkable
    class BoundProvider(Protocol):
        async def ainvoke(self, input: list[BaseMessage], **kwargs) -> AIMessage: ...
        def astream(self, input: list[BaseMessage], **kwargs) -> AsyncIterator[AIMessageChunk]: ...

    @runtime_checkable
    class LLMProvider(Protocol):
        def get_provider_name(self) -> str: ...
        async def validate_config(self) -> ProbeError | None: ...
        def bind_tools(self, tools: Sequence[BaseTool]) -> BoundProvider: ...
        async def list_models(self) -> list[str]: ...

The Protocols are NOT subclasses of ``BaseChatModel`` — they are structural,
duck-typed surfaces. The ``BoundProvider`` Protocol exists separately because
``BaseChatModel.bind_tools(...)`` returns ``Runnable[LanguageModelInput, AIMessage]``,
NOT a ``BaseChatModel`` (verified against installed ``langchain-core`` 1.x).

Wave 0 stub: skip with the future-truth annotation. Wave 1 replaces the skip body
with ``isinstance(provider, LLMProvider)`` for each concrete provider class.
"""

import pytest

pytestmark = pytest.mark.unit


def test_protocols_are_runtime_checkable() -> None:
    """LLMProvider and BoundProvider are runtime_checkable Protocols.

    Wave 1 future-truth assertions:
        - ``isinstance(OllamaProvider(...), LLMProvider) is True``
        - ``isinstance(OpenAIProvider(...), LLMProvider) is True``
        - ``isinstance(AnthropicProvider(...), LLMProvider) is True``
        - ``BoundProvider`` does NOT inherit ``bind_tools`` (the bound Runnable
          returned by ``LangChain.bind_tools`` exposes ``ainvoke`` + ``astream`` only).
        - ``LLMProvider`` is NOT a subclass of ``BaseChatModel`` — it's structural.
    """
    pytest.skip("Wave 1 implements LLMProvider + BoundProvider Protocols")
