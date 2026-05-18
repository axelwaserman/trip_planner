"""Protocol conformance tests for the LLMProvider abstraction (Phase 4.5).

Asserts that each concrete provider class structurally satisfies the
``@runtime_checkable`` ``LLMProvider`` Protocol, and that no concrete provider
class accidentally also satisfies the ``BoundProvider`` Protocol — only the
runnable returned by ``LLMProvider.bind_tools(...)`` should match
``BoundProvider``.

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
"""

from app.llm.protocol import BoundProvider, LLMProvider
from app.llm.providers.anthropic import AnthropicProvider
from app.llm.providers.ollama import OllamaProvider
from app.llm.providers.openai import OpenAIProvider


def test_ollama_provider_satisfies_llm_provider_protocol() -> None:
    """``isinstance(OllamaProvider(...), LLMProvider)`` is True."""
    provider = OllamaProvider(model="qwen3:4b", base_url="http://localhost:11434", probe_timeout_seconds=1.5)
    assert isinstance(provider, LLMProvider)


def test_openai_provider_satisfies_llm_provider_protocol() -> None:
    """``isinstance(OpenAIProvider(...), LLMProvider)`` is True."""
    provider = OpenAIProvider(model="gpt-4o-mini", api_key="sk-test")
    assert isinstance(provider, LLMProvider)


def test_anthropic_provider_satisfies_llm_provider_protocol() -> None:
    """``isinstance(AnthropicProvider(...), LLMProvider)`` is True."""
    provider = AnthropicProvider(model="claude-3-5-sonnet-20241022", api_key="sk-ant-test")
    assert isinstance(provider, LLMProvider)


def test_raw_providers_do_not_satisfy_bound_provider_protocol() -> None:
    """Raw providers are NOT BoundProviders — only the result of bind_tools is.

    Each raw provider exposes ``bind_tools`` (an LLMProvider member) but the
    BoundProvider Protocol requires ``ainvoke`` + ``astream``. The structural
    isinstance check fails because the raw classes have neither.
    """
    ollama = OllamaProvider(model="qwen3:4b", base_url="http://localhost:11434", probe_timeout_seconds=1.5)
    openai = OpenAIProvider(model="gpt-4o-mini", api_key="sk-test")
    anthropic = AnthropicProvider(model="claude-3-5-sonnet-20241022", api_key="sk-ant-test")
    assert not isinstance(ollama, BoundProvider)
    assert not isinstance(openai, BoundProvider)
    assert not isinstance(anthropic, BoundProvider)
