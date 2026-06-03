# ADR-007: PydanticAI Agent Pattern

**Date**: 2026-06-03
**Status**: Locked
**Supersedes**: ADR-001 (LangChain 1.0 with bind_tools())

<!-- Plain-text mirror for grep-based verification: -->
<!-- Status: Locked -->


## Context

Phase 5 replaces LangChain's `bind_tools()` / `BaseChatModel` / `astream()`
surface with PydanticAI's `Agent[Deps, str]` / `agent.iter()` surface. The
LangChain layer carried three pieces of debt that PydanticAI closes natively:

1. **Two-tier provider shape.** `LLMProvider.bind_tools(tools) -> BoundProvider`
   was forced by LangChain returning `Runnable` from `bind_tools`, not the
   original `BaseChatModel`. PydanticAI's `Agent` IS the tool-bound thing —
   there is no second tier.
2. **Protocol-vs-ABC mismatch.** `LLMProvider` and `BoundProvider` were
   `typing.Protocol` (with `@runtime_checkable`) when the project rule in
   `CLAUDE.md` requires `abc.ABC` for in-project interfaces ("Abstract
   interfaces use `ABC`, never `Protocol`"). Carried as "Known Tech Debt" in
   `ARCHITECTURE.md` through Phase 4.x.
3. **Monkey-patched tool DI.** `search_flights._flight_client = flight_client`
   in `lifespan` was the only way to inject the `FlightAPIClient` into the
   `@tool`-decorated function. Carried as "Monkey-Patched Tool Dependency"
   anti-pattern in `ARCHITECTURE.md`.

PydanticAI provides `RunContext[Deps]` for framework-managed tool DI,
single-tier `Agent[Deps, str]` per session, and native `<think>` tag parsing
via `ModelProfile.thinking_tags` for Ollama qwen3 — addressing all three.

The migration was resequenced ahead of Phase 6 Postgres on 2026-06-02 (PR #20
review) so the conversation-history shape chosen here (PydanticAI's
`list[ModelMessage]`) directly drives Phase 6's `Message` SQLModel.

## Decision

Use **`pydantic-ai>=0.8.1`** as the single chat-agent runtime.

**Provider abstraction (D-01..D-04, D-10):**

```python
class LLMProvider(ABC):
    @abstractmethod
    def get_provider_name(self) -> str: ...
    @abstractmethod
    async def validate_config(self) -> ProbeError | None: ...
    @abstractmethod
    async def list_models(self) -> list[str]: ...
    @abstractmethod
    def build_agent(
        self, tools: Sequence[Any], deps_type: type[Any]
    ) -> Agent[Any, str]: ...
```

`LLMProviderFactory.build()` returns the concrete `LLMProvider`; `ChatService`
calls `provider.build_agent(tools=[search_flights], deps_type=ChatDeps)` per
session and stores the resulting `Agent[ChatDeps, str]` keyed by `session_id`.
The Phase 4.5 `_bound_providers` dict becomes `_agents: dict[str, Agent[ChatDeps, str]]`.

**Tool DI via `RunContext` (D-05..D-07):**

```python
@dataclass(frozen=True)
class ChatDeps:
    flight_client: FlightAPIClient
    session_id: str
    user_id: str

async def search_flights(
    ctx: RunContext[ChatDeps],
    origin: str, destination: str, departure_date: str, ...
) -> str:
    client = ctx.deps.flight_client
    ...
```

The `search_flights._flight_client` attribute back-door is **deleted**, not
retained as a fallback.

**Streaming via `agent.iter()` (D-12, D-15):**

`ChatService.chat_stream()` walks `agent.iter()` nodes. `ModelRequestNode.stream()`
yields `ModelResponseStreamEvent` (`PartStartEvent`, `PartDeltaEvent`,
`FinalResultEvent`); `CallToolsNode.stream()` yields `HandleResponseEvent`
(`FunctionToolCallEvent`, `FunctionToolResultEvent`). Each PydanticAI event
maps to one of five `StreamEvent` ABC subclasses (`ContentEvent`,
`ThinkingEvent`, `ToolCallEvent`, `ToolResultEvent`, `ErrorEvent`). The SSE
wire format is byte-identical to Phase 4.7 — frontend `parseSSE.ts` is
unchanged.

**Conversation history (D-08, D-11):**

```python
class ConversationStore(ABC):
    @abstractmethod
    async def append(self, session_id: str, messages: list[ModelMessage]) -> None: ...
    @abstractmethod
    async def load(self, session_id: str) -> list[ModelMessage]: ...
    @abstractmethod
    async def delete(self, session_id: str) -> None: ...
    @abstractmethod
    async def list_for_user(self, user_id: str) -> list[ConversationInfo]: ...
```

`InMemoryConversationStore` ships in Phase 5; `PostgresConversationStore`
swaps in via DI in Phase 6 with no `ChatService` change.

**Test mocking (D-17, D-18):**

`_MockLLMProvider.build_agent()` returns `Agent(FunctionModel(stream_function=...), tools=..., deps_type=...)`,
not a fake `Agent` — the real PydanticAI streaming code path runs in tests.
The Phase 4.4 locked scenarios (`greeting`, `single_tool_call`, `multi_turn`)
are preserved verbatim. `make_chat_service_with_mock_llm()` factory signature
is unchanged.

## Verification

All five Open Questions from `05-CONTEXT.md` were verified against installed
`pydantic-ai 0.8.1` source — see `.planning/phases/05-pydanticai-migration/05-RESEARCH.md`
§ Verified Open Questions for the full evidence trail. Confidence is **HIGH**
on all five (live execution + source inspection).

| OQ | Question | Verdict | Source |
|----|----------|---------|--------|
| **OQ-01** | Does `class Foo(BaseModel, ABC)` + `Field(discriminator='type')` work cleanly in Pydantic v2? | YES — clean. No abstract methods on `StreamEvent`; concrete subclasses narrow `type: str` to `Literal[...]`. | Live execution against pydantic 2.12.3 |
| **OQ-02** | PydanticAI stream event types — exact names and attributes? | CONFIRMED. `ThinkingPart.content`, `ThinkingPartDelta.content_delta`, `TextPart.content`, `TextPartDelta.content_delta`, `ToolCallPart.{tool_name, args, tool_call_id}`, `ToolReturnPart.{tool_name, content, tool_call_id}`, `FunctionToolCallEvent`, `FunctionToolResultEvent`. | `pydantic_ai.messages` source |
| **OQ-03** | `OpenAIResponsesModel` availability for o-series reasoning models? | YES — exported from `pydantic_ai.models.openai`. Provider dispatch on `_O_SERIES_PREFIXES = ("o1", "o3")`. Auth shape is plain `str`, no `SecretStr`. | `pydantic_ai.models.openai` source |
| **OQ-04** | Does PydanticAI parse qwen3 `<think>` tags into `ThinkingPart` natively for Ollama? | YES — via `ModelProfile.thinking_tags` (default `('<think>', '</think>')`) + `handle_text_delta`. No `reasoning=True` flag needed. | `pydantic_ai._thinking_part`, `_parts_manager`, `models/openai.py` source |
| **OQ-05** | `ModelMessagesTypeAdapter` JSON serialization round-trip stability? | CONFIRMED — stable. Import path: `from pydantic_ai.messages import ModelMessagesTypeAdapter` (NOT from `pydantic_ai`). | Live execution + source |

## Per-Provider Migration Rules

Concrete provider classes wrap `pydantic_ai.models.*` with the matching
provider — see `05-RESEARCH.md` § Per-Provider Migration Rules for the full
code snippets. Summary:

| Provider | PydanticAI model | PydanticAI provider | Thinking surface |
|----------|------------------|---------------------|------------------|
| Ollama | `OpenAIChatModel(model, provider=OllamaProvider(base_url=...))` | `pydantic_ai.providers.ollama.OllamaProvider` | Native `<think>` tag parsing via default `thinking_tags`. No `reasoning=True` flag. |
| OpenAI | `OpenAIChatModel(model, provider=OpenAIProvider(api_key=...))` (standard) or `OpenAIResponsesModel(...)` (o-series) | `pydantic_ai.providers.openai.OpenAIProvider` | `ThinkingPart` only via Responses API (o-series). Standard models emit no `ThinkingPart`. |
| Anthropic | `AnthropicModel(model, provider=AnthropicProvider(api_key=...))` | `pydantic_ai.providers.anthropic.AnthropicProvider` | Native via `BetaThinkingBlock` / `BetaThinkingDelta`. `validate_config()` MUST run before `build_agent()` (else `UserError`). |
| LM Studio | `OpenAIChatModel(model, provider=OpenAIProvider(base_url=..., api_key=None))` | `pydantic_ai.providers.openai.OpenAIProvider` | Best-effort: default `thinking_tags` parses `<think>` if model emits them. The Phase 4.5 `api_key="lm-studio"` sentinel is dropped. |

## Consequences

**Code surface:**

- **Wave 1**: `LLMProvider(ABC)` + `LLMProviderFactory` return-type swap +
  `ChatDeps` dataclass. (Foundation; one-tier shape collapses.)
- **Wave 2**: Four concrete providers reshaped against PydanticAI models +
  `ConversationStore(ABC)` + `InMemoryConversationStore`.
- **Wave 3**: `ChatService.chat_stream()` rewrite against `agent.iter()`;
  `search_flights` signature gains `ctx: RunContext[ChatDeps]`; `_flight_client`
  back-door deleted; `StreamEvent(BaseModel, ABC)` ABC refactor lands here.
- **Wave 4**: `pyproject.toml` swap — remove `langchain`, `langchain-core`,
  `langchain-ollama`, `langchain-openai`, `langchain-anthropic`, and
  `langgraph` (PR #1 left this entry); add `pydantic-ai>=0.8.1`. Bump
  `pydantic>=2.12` to match pydantic-ai-slim's floor.
- **Wave 5**: Documentation — this ADR locks; ADR-001 flips to Superseded;
  `ARCHITECTURE.md` + `PROJECT.md` updated.

**Closes:**

- ARCHITECTURE.md "Known Tech Debt: `app/llm/protocol.py` uses `typing.Protocol`" — single `LLMProvider(ABC)` is the canonical shape.
- ARCHITECTURE.md "Monkey-Patched Tool Dependency" anti-pattern — `RunContext[ChatDeps]` is the framework-managed replacement.
- The `BoundProvider` tier — retired entirely; no compatibility shim.

**Wire format:**

- SSE event JSON is byte-identical to Phase 4.7. Frontend `parseSSE.ts`,
  `useChat.ts`, `types/chat.ts` are unchanged. Verified by golden-file test
  in `tests/unit/chat/test_stream_event_wire_compat.py`.

**Test posture:**

- Default `pytest` (unit + integration via path discovery) stays fast and
  offline — no Ollama, no real cloud. `_MockLLMProvider` uses
  `FunctionModel(stream_function=...)` so the real PydanticAI streaming code
  path runs in tests.
- Per-provider thinking-token acceptance tests (D-13) are gated on env vars /
  local daemons via `@pytest.mark.skipif`, mirroring the Phase 4.5 pattern.

**Open risks** (carried forward to later phases):

- **OQ-R1**: `ModelMessagesTypeAdapter` serialization may evolve between
  pydantic-ai minor versions. Phase 6 must store the pydantic-ai version
  alongside serialized messages in the `Conversation` table.
- **OQ-R2**: Anthropic extended thinking may require explicit
  `extra_headers={"anthropic-beta": "thinking-in-streaming"}`. Surfaces in
  the D-13 acceptance test.

## Supersedes

ADR-001 (LangChain 1.0 with bind_tools()) — see
`.planning/adrs/ADR-001-langchain.md`. The `Status: Superseded by ADR-007`
header on ADR-001 reflects this transition.
