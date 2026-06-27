# Phase 5: PydanticAI Migration - Research

**Researched:** 2026-06-03
**Domain:** PydanticAI 0.8.1 — Agent, streaming, tool DI via RunContext, provider models, ABC migration, mock testing
**Confidence:** HIGH (all open questions verified against installed pydantic-ai 0.8.1 source and PyPI metadata)

---

## Summary

Phase 5 replaces LangChain's `bind_tools()` / `BaseChatModel` / `astream()` surface with PydanticAI's `Agent[ChatDeps, str]` / `agent.run_stream()` / `agent.iter()` surface. The migration is straightforward: PydanticAI is a purpose-built agent framework that makes most of the LangChain workarounds (monkey-patched `_flight_client`, two-Protocol shape, `chunk.additional_kwargs["reasoning_content"]`) unnecessary.

All five locked Open Questions (OQ-01 through OQ-05) are now resolved with HIGH confidence against installed pydantic-ai 0.8.1. The primary non-obvious architectural finding: for `ChatService.chat_stream()` to yield tool call and tool result events live (interleaved with content), **`agent.iter()` is the correct API**. `agent.run_stream()` handles tools silently in `on_complete()` and does not expose them as a live stream unless `event_stream_handler` is also set — but using a handler alongside `run_stream` requires an asyncio queue bridge, which is more complex than `iter()`.

**Primary recommendation:** Use `agent.iter()` + per-node streaming (`ModelRequestNode.stream()` for model events, `CallToolsNode.stream()` for tool events) as the main loop in `ChatService.chat_stream()`. Use `agent_run.result.new_messages()` after `End` to append history to `ConversationStore`.

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01:** Single `LLMProvider(ABC)` with `build_agent(tools, deps_type) -> Agent`. `BoundProvider` retires.
- **D-02:** ABC surface: `get_provider_name()`, `validate_config()` (returns `ProbeError | None`), `list_models()`, `build_agent(tools: Sequence, deps_type: type[Deps]) -> Agent[Deps, str]`.
- **D-03:** ABC, not Protocol — closes the ARCHITECTURE.md "Known Tech Debt" entry.
- **D-04:** `LLMProviderFactory.build()` returns the concrete `LLMProvider`; ChatService calls `provider.build_agent(...)` per session. `_bound_providers` dict becomes `_agents: dict[str, Agent[ChatDeps, str]]`.
- **D-05:** `ChatDeps` frozen dataclass: `flight_client: FlightAPIClient`, `session_id: str`, `user_id: str`.
- **D-06:** `search_flights` gains `ctx: RunContext[ChatDeps]` as first parameter; reads `ctx.deps.flight_client`.
- **D-07:** Tool registration via `Agent(model, tools=[search_flights], deps_type=ChatDeps)` at agent construction; `agent.run_stream(..., deps=ChatDeps(...))` per turn.
- **D-08:** `ConversationStore(ABC)` + `InMemoryConversationStore` in Phase 5; Phase 6 swaps in `PostgresConversationStore`.
- **D-09:** `_metadata` and `_last_activity` dicts stay on ChatService.
- **D-10:** `_bound_providers` becomes `_agents: dict[str, Agent[ChatDeps, str]]`.
- **D-11:** Storage format inside `InMemoryConversationStore` is `list[ModelMessage]`.
- **D-12:** All four providers emit `ThinkingEvent` best-effort wherever PydanticAI surfaces `ThinkingPart`/`ThinkingPartDelta`.
- **D-13:** Per-provider acceptance test confirms thinking flow, gated on local daemon or API key.
- **D-14:** OpenAI o-series requires `OpenAIResponsesModel` dispatch.
- **D-15:** `StreamEvent` becomes `class StreamEvent(BaseModel, ABC)` with five concrete subclasses.
- **D-16:** REQ-p5-stream-event-abc bundled into Phase 5.
- **D-17:** `MockLLMStream` updated to drive PydanticAI agent surface.
- **D-18:** `make_chat_service_with_mock_llm()` factory signature unchanged; internals rewritten.
- **D-19:** Default `pytest` stays fast and offline.
- **D-20:** `langchain*` removed from `pyproject.toml`; `pydantic-ai` added.
- **D-21:** ADR-001 → Superseded; ADR-007 → Locked.

### Claude's Discretion

- `app/llm/protocol.py` may rename to `app/llm/base.py` (it's now an ABC).
- Concrete `pydantic_ai.models.*` class per provider.
- Whether to surface `usage` (token counts) on `ContentEvent` for Phase 8 telemetry.
- Whether `ConversationStore.delete` exists in Phase 5 ABC.
- LM Studio sentinel `api_key="lm-studio"` survival.

### Deferred Ideas (OUT OF SCOPE)

- Postgres-backed conversation store → Phase 6.
- `Conversation` renaming → Phase 6.
- `SessionCreateRequest` SRP split → Phase 6.
- `ProviderInfo` SRP split → Phase 6.
- `PostgresUserRepository` + DB seeding → Phase 6.
- `Depends(get_flight_client)` residual route plumbing → Phase 6.
- Token-usage telemetry on `ContentEvent` → Phase 8.
- Typed Pydantic output for `search_flights` → Phase 7.
- OpenAI Responses API reasoning-token observability → Phase 8.
- Anthropic prompt caching headers → Phase 8 or v2.
- Multi-agent patterns → v2.
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| REQ-pydantic-ai-migration | Replace LangChain with PydanticAI Agent; preserve SSE event contract; remove langchain* deps; convert Protocols to ABCs; reshape providers; replace `_flight_client` back-door with RunContext DI | Verified: Agent API, RunContext, provider model classes, streaming loop, tool registration — all confirmed against pydantic-ai 0.8.1 source |
| REQ-p5-stream-event-abc | Refactor StreamEvent discriminated-union alias into `StreamEvent(BaseModel, ABC)` base class with five concrete subclasses | Verified: `class Foo(BaseModel, ABC)` + `Field(discriminator='type')` work cleanly in Pydantic v2 — see OQ-01 resolution |
</phase_requirements>

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| LLM agent execution + tool calling | API/Backend (ChatService) | — | PydanticAI Agent lives server-side; client only sees SSE events |
| Per-session agent construction | API/Backend (ChatService.create_session) | — | Agent is bound to provider model; must be scoped per session |
| Tool dependency injection (FlightAPIClient) | API/Backend (RunContext[ChatDeps]) | — | D-06 closes the monkey-patch back-door; injection is framework-managed |
| Streaming event extraction (ThinkingPart, TextPart, ToolCallPart) | API/Backend (chat_stream loop) | — | PydanticAI emits model events from iter() nodes; ChatService maps them to StreamEvent subclasses |
| Conversation history storage | API/Backend (ConversationStore) | — | D-08: InMemoryConversationStore in Phase 5; PostgresConversationStore in Phase 6 |
| SSE wire format | API/Backend (routes.py) | Frontend (parseSSE.ts) | Frontend-facing SSE contract is unchanged; only the Python-side event ABC changes |
| Provider model selection | API/Backend (LLMProviderFactory) | — | Factory dispatches on config.provider to concrete LLMProvider subclasses |

---

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| pydantic-ai | 0.8.1 [VERIFIED: PyPI] | Agent framework; model abstraction; tool DI; streaming | Official Pydantic project; replaces LangChain per D-20 |
| pydantic | >=2.12 [VERIFIED: pydantic-ai-slim METADATA] | Model validation; discriminated unions; BaseModel+ABC | Already in project; pydantic-ai requires >=2.12 |

**Note:** `pydantic-ai` 0.8.1 is a meta-package that depends on `pydantic-ai-slim` 0.8.1 (the actual slim core). Both have the same version number. Installing `pydantic-ai` in `pyproject.toml` is correct.

**pyproject.toml floor:** The current `pydantic>=2.9.0` must be raised to `pydantic>=2.12` to match pydantic-ai-slim's requirement. The installed version (2.12.3) already satisfies this. [VERIFIED: pydantic-ai-slim 0.8.1 METADATA]

**`langgraph` in pyproject.toml:** `langgraph>=1.0.2` is still present in `pyproject.toml` despite PR #1 claiming removal. Phase 5 must clean this up along with `langchain*`. [VERIFIED: codebase inspection]

**Installation command:**
```bash
uv add pydantic-ai
uv remove langchain langchain-core langchain-ollama langchain-openai langchain-anthropic langgraph
```

---

## Package Legitimacy Audit

| Package | Registry | Age | Downloads | Source Repo | slopcheck | Disposition |
|---------|----------|-----|-----------|-------------|-----------|-------------|
| pydantic-ai | PyPI | ~8 months (first release 2024) | High (Pydantic official) | github.com/pydantic/pydantic-ai | OK (slopcheck ran; flagged naming pattern but confirmed established) | Approved |

**slopcheck verdict:** `[OK]` — "Name ends with '-ai' — classic LLM naming pattern. Name looks like LLM bait but package is established." Confirmed official Pydantic project (Samuel Colvin + team as authors, `pydantic.dev` email, official GitHub). [VERIFIED: slopcheck 0.6.1 + PyPI metadata]

**Postinstall scripts:** None. Entry point is only the `pai` CLI (`pydantic_ai._cli:cli_exit`). [VERIFIED: dist-info inspection]

**Packages removed due to slopcheck:** none
**Packages flagged as suspicious:** none

---

## Verified Open Questions

### OQ-01: Does `class Foo(BaseModel, ABC)` + `Field(discriminator='type')` work cleanly?

**Verdict: YES — clean in Pydantic v2.** [VERIFIED: live execution against pydantic 2.12.3]

Tested pattern:
```python
from pydantic import BaseModel, Field
from abc import ABC
from typing import Annotated, Literal, Union

class StreamEvent(BaseModel, ABC):
    type: str
    session_id: str

class ContentEvent(StreamEvent):
    type: Literal["content"] = "content"
    chunk: str = ""

class ThinkingEvent(StreamEvent):
    type: Literal["thinking"] = "thinking"
    chunk: str = ""

# All of these work:
c = ContentEvent(session_id="abc")         # instantiation OK
isinstance(c, StreamEvent)                  # True
isinstance(c, ABC)                          # True
c.model_dump_json()                         # '{"type":"content","session_id":"abc","chunk":""}'
TypeAdapter(Annotated[Union[...], Field(discriminator="type")]).validate_python(...)  # OK
```

**Constraints:**
- Do NOT declare `@abstractmethod` methods on `StreamEvent` unless all five concrete subclasses implement them. Using ABC purely as a mixin for `isinstance` checks (no abstract methods) works perfectly.
- The `type: str` field on the base class is fine — concrete subclasses narrow it to `Literal[...]`.
- The SSE wire format (`model_dump_json()`) is unchanged.

**Planner rule:** Use `class StreamEvent(BaseModel, ABC)` with no abstract methods. The `Annotated[..., Field(discriminator="type")]` union alias in Phase 4.7 is retired; consumers reference `StreamEvent` as the type annotation. The five concrete subclasses remain unchanged except they now explicitly subclass `StreamEvent`.

---

### OQ-02: PydanticAI stream event types — exact names and attributes

**Verdict: CONFIRMED.** [VERIFIED: pydantic-ai 0.8.1 source, `messages.py`]

#### Complete Part/Delta Class Inventory

| Class | Module | Key Attributes |
|-------|--------|----------------|
| `TextPart` | `pydantic_ai.messages` | `content: str`, `part_kind: Literal['text']` |
| `ThinkingPart` | `pydantic_ai.messages` | `content: str`, `id: str \| None`, `signature: str \| None`, `part_kind: Literal['thinking']` |
| `ToolCallPart` | `pydantic_ai.messages` | `tool_name: str`, `args: str \| dict[str,Any] \| None`, `tool_call_id: str`, `part_kind: Literal['tool-call']` |
| `ToolReturnPart` | `pydantic_ai.messages` | `tool_name: str`, `content: Any`, `tool_call_id: str`, `part_kind: Literal['tool-return']` |
| `TextPartDelta` | `pydantic_ai.messages` | `content_delta: str`, `part_delta_kind: Literal['text']` |
| `ThinkingPartDelta` | `pydantic_ai.messages` | `content_delta: str \| None`, `signature_delta: str \| None`, `part_delta_kind: Literal['thinking']` |
| `ToolCallPartDelta` | `pydantic_ai.messages` | `tool_name_delta: str \| None`, `args_delta: str \| dict \| None`, `tool_call_id: str \| None`, `part_delta_kind: Literal['tool_call']` |
| `PartStartEvent` | `pydantic_ai.messages` | `index: int`, `part: ModelResponsePart`, `event_kind: Literal['part_start']` |
| `PartDeltaEvent` | `pydantic_ai.messages` | `index: int`, `delta: ModelResponsePartDelta`, `event_kind: Literal['part_delta']` |
| `FunctionToolCallEvent` | `pydantic_ai.messages` | `part: ToolCallPart`, `event_kind: Literal['function_tool_call']` |
| `FunctionToolResultEvent` | `pydantic_ai.messages` | `result: ToolReturnPart \| RetryPromptPart`, `event_kind: Literal['function_tool_result']` |
| `FinalResultEvent` | `pydantic_ai.messages` | `tool_name: str \| None`, `tool_call_id: str \| None`, `event_kind: Literal['final_result']` |

**Important:** `content_delta` (not `delta`, not `chunk`, not `text`) is the attribute name on `TextPartDelta` and `ThinkingPartDelta`.

---

## Stream Event Type Map

The `chat_stream()` loop iterates nodes via `agent.iter()`. The mapping from PydanticAI events to `StreamEvent` subclasses:

| StreamEvent subclass | Source PydanticAI event(s) | Extraction rule |
|---|---|---|
| `ThinkingEvent` | `PartDeltaEvent` where `isinstance(delta, ThinkingPartDelta)` | `chunk = event.delta.content_delta or ""` |
| `ThinkingEvent` | `PartStartEvent` where `isinstance(part, ThinkingPart)` | `chunk = event.part.content` (full content if model sends it in start) |
| `ContentEvent` | `PartDeltaEvent` where `isinstance(delta, TextPartDelta)` | `chunk = event.delta.content_delta` |
| `ContentEvent` | `PartStartEvent` where `isinstance(part, TextPart)` | `chunk = event.part.content` (non-empty start content) |
| `ToolCallEvent` | `FunctionToolCallEvent` | `tool_name = event.part.tool_name`, `tool_args = event.part.args if isinstance(event.part.args, dict) else json.loads(event.part.args or "{}")` |
| `ToolResultEvent` | `FunctionToolResultEvent` where `isinstance(result, ToolReturnPart)` | `tool_name = event.result.tool_name`, `tool_result = str(event.result.content)`, `elapsed_ms` computed from wall-clock diff |
| `ErrorEvent` | Exception in streaming loop or `FunctionToolResultEvent` where `isinstance(result, RetryPromptPart)` | Mapped via existing `_scrub` + `ProbeError` chain |

### Match block pattern for the `agent.iter()` streaming loop

```python
from pydantic_ai import Agent, ModelRequestNode, CallToolsNode
from pydantic_ai.messages import (
    PartStartEvent, PartDeltaEvent, FinalResultEvent,
    TextPart, ThinkingPart, ToolCallPart,
    TextPartDelta, ThinkingPartDelta, ToolCallPartDelta,
    FunctionToolCallEvent, FunctionToolResultEvent,
    ToolReturnPart, RetryPromptPart,
)

# Inside ChatService.chat_stream():
history = await self._conversation_store.load(session_id)
deps = ChatDeps(
    flight_client=self._flight_client,
    session_id=session_id,
    user_id=self._metadata[session_id]["user_id"],
)
agent: Agent[ChatDeps, str] = self._agents[session_id]

async with agent.iter(
    message,
    message_history=history,
    deps=deps,
) as agent_run:
    async for node in agent_run:
        if isinstance(node, ModelRequestNode):
            # Stream model response events (TextPart, ThinkingPart deltas)
            async with node.stream(agent_run.ctx) as model_stream:
                async for event in model_stream:
                    match event:
                        case PartStartEvent(part=ThinkingPart(content=c)) if c:
                            yield ThinkingEvent(chunk=c, session_id=session_id)
                        case PartDeltaEvent(delta=ThinkingPartDelta(content_delta=d)) if d:
                            yield ThinkingEvent(chunk=d, session_id=session_id)
                        case PartStartEvent(part=TextPart(content=c)) if c:
                            yield ContentEvent(chunk=c, session_id=session_id)
                        case PartDeltaEvent(delta=TextPartDelta(content_delta=d)) if d:
                            yield ContentEvent(chunk=d, session_id=session_id)
        elif isinstance(node, CallToolsNode):
            # Tool execution events (FunctionToolCallEvent, FunctionToolResultEvent)
            async with node.stream(agent_run.ctx) as tool_stream:
                async for event in tool_stream:
                    match event:
                        case FunctionToolCallEvent(part=ToolCallPart() as part):
                            tool_args = (
                                part.args if isinstance(part.args, dict)
                                else json.loads(part.args or "{}")
                            )
                            yield ToolCallEvent(
                                tool_name=part.tool_name,
                                tool_args=tool_args,
                                session_id=session_id,
                            )
                            self._metadata[session_id]["last_tool_invocation"] = {
                                "tool_name": part.tool_name,
                                "tool_args": tool_args,
                                "tool_call_id": part.tool_call_id,
                            }
                        case FunctionToolResultEvent(result=ToolReturnPart() as ret):
                            yield ToolResultEvent(
                                tool_name=ret.tool_name,
                                tool_result=str(ret.content),
                                elapsed_ms=0,  # PydanticAI handles timing internally
                                session_id=session_id,
                            )

# After End node, persist new messages
if agent_run.result is not None:
    new_msgs = agent_run.result.new_messages()
    await self._conversation_store.append(session_id, new_msgs)
```

**Key API facts confirmed:**
- `agent.iter(...)` returns an `AsyncContextManager[AgentRun]`. [VERIFIED: source]
- `async for node in agent_run` yields `UserPromptNode | ModelRequestNode | CallToolsNode | End`. [VERIFIED: source]
- `ModelRequestNode.stream(ctx)` is an `AsyncContextManager` that yields `AgentStream`; `async for event in model_stream` yields `ModelResponseStreamEvent` (= `PartStartEvent | PartDeltaEvent | FinalResultEvent`). [VERIFIED: `AgentStream.__aiter__` source]
- `CallToolsNode.stream(ctx)` is an `AsyncContextManager` yielding `HandleResponseEvent` (= `FunctionToolCallEvent | FunctionToolResultEvent | BuiltinToolCallEvent | BuiltinToolResultEvent`). [VERIFIED: source]
- `agent_run.result.new_messages()` returns `list[ModelMessage]` (only the messages from this run, not history). [VERIFIED: `AgentRunResult.new_messages` source]

---

### OQ-03: `OpenAIResponsesModel` availability

**Verdict: YES — exported from `pydantic_ai.models.openai`.** [VERIFIED: pydantic-ai 0.8.1 source]

```python
from pydantic_ai.models.openai import OpenAIChatModel, OpenAIResponsesModel
from pydantic_ai.providers.openai import OpenAIProvider
```

- `OpenAIChatModel` — for all standard OpenAI models (`gpt-4o`, `gpt-4o-mini`, etc.)
- `OpenAIResponsesModel` — for o-series reasoning models (`o1`, `o1-mini`, `o3`, `o3-mini`); uses the Responses API (not Chat Completions)

**Provider options differ:**
- `OpenAIChatModel` accepts providers: `'azure', 'deepseek', 'cerebras', 'fireworks', 'github', 'grok', 'heroku', 'moonshotai', 'openai', 'openai-chat', 'openrouter', 'together', 'vercel'`, or `Provider[AsyncOpenAI]`
- `OpenAIResponsesModel` accepts: `'openai', 'deepseek', 'azure', 'openrouter', 'grok', 'fireworks', 'together'`, or `Provider[AsyncOpenAI]`
- **Neither accepts `'ollama'` as a string literal** — use `OllamaProvider(base_url=...)` directly

**Auth shape:** Plain `str` (not `SecretStr`). PydanticAI passes it directly to `AsyncOpenAI`.

**Planner rule for D-14 dispatch:**
```python
from pydantic_ai.models.openai import OpenAIChatModel, OpenAIResponsesModel
from pydantic_ai.providers.openai import OpenAIProvider

_O_SERIES_PREFIXES = ("o1", "o3")  # lives on Settings per CLAUDE.md

def build_agent(self, tools, deps_type):
    provider = OpenAIProvider(api_key=self._api_key)
    if any(self._model.startswith(p) for p in _O_SERIES_PREFIXES):
        model = OpenAIResponsesModel(self._model, provider=provider)
    else:
        model = OpenAIChatModel(self._model, provider=provider)
    return Agent(model, tools=list(tools), deps_type=deps_type)
```

---

### OQ-04: Does PydanticAI parse qwen3 `<think>` tags into `ThinkingPart` natively for Ollama?

**Verdict: YES — parsed natively via `thinking_tags` in `ModelProfile`.** [VERIFIED: pydantic-ai 0.8.1 `_thinking_part.py`, `_parts_manager.py`, `models/openai.py`]

`ModelProfile.thinking_tags` defaults to `('<think>', '</think>')`. The `OllamaProvider` uses `qwen_model_profile` for qwen models, which does NOT override `thinking_tags` — the default pair is inherited.

During streaming (`OpenAIStreamedResponse._get_event_iterator`), each text delta is passed through `handle_text_delta(..., thinking_tags=self._model_profile.thinking_tags)`. When the accumulator sees `<think>`, it switches to a `ThinkingPart` accumulator until `</think>`. The final streamed `PartDeltaEvent` will have `delta=ThinkingPartDelta(content_delta=<thinking content>)`.

**Additionally**, Ollama may also return thinking content via `choice.delta.reasoning_content` (the DeepSeek pattern). PydanticAI handles both: if `reasoning_content` is present it goes directly to `handle_thinking_delta`.

**Planner rule:** `OllamaProvider.build_agent()` does NOT need any special reasoning flags or config. The `OllamaProvider` profile handles `<think>` tag splitting automatically. The `reasoning=True` LangChain parameter that existed in Phase 4.5's `ChatOllama` is NOT needed and has no PydanticAI equivalent.

---

### OQ-05: `ModelMessagesTypeAdapter` JSON serialization round-trip stability

**Verdict: CONFIRMED — stable round-trip.** [VERIFIED: live execution against pydantic-ai 0.8.1]

```python
from pydantic_ai.messages import ModelMessagesTypeAdapter

# Serialize
json_bytes: bytes = ModelMessagesTypeAdapter.dump_json(messages)

# Deserialize
restored: list[ModelMessage] = ModelMessagesTypeAdapter.validate_json(json_bytes)
```

**Import path:** `pydantic_ai.messages.ModelMessagesTypeAdapter` (NOT `pydantic_ai.ModelMessagesTypeAdapter` — that does not exist in the public `__init__.py` exports). [VERIFIED: source]

**Implementation note:** `ModelMessagesTypeAdapter = pydantic.TypeAdapter(list[ModelMessage], config=ConfigDict(defer_build=True, ser_json_bytes='base64', val_json_bytes='base64'))`. The base64 config is for binary content in messages (images etc.); standard text messages round-trip cleanly.

**Phase 6 note:** `PostgresConversationStore` will use `ModelMessagesTypeAdapter.dump_json(messages)` → store bytes in a JSON column → `ModelMessagesTypeAdapter.validate_json(stored_bytes)` on load. The schema is version-coupled to the pydantic-ai version — upgrading pydantic-ai in Phase 6+ requires a migration strategy if the `ModelMessage` serialization format changes between versions. Flag this as an open risk.

---

## Additional Planner-Relevant Questions (Resolved)

### Does PydanticAI expose `TestModel` or `FunctionModel` for mock testing?

**Verdict: YES — `TestModel` and `FunctionModel` both exist.** [VERIFIED: pydantic-ai 0.8.1 `models/test.py`, `models/function.py`]

**`TestModel`** (`from pydantic_ai.models.test import TestModel`):
- Constructor: `TestModel(*, call_tools='all', custom_output_text=None, seed=0)`
- By default calls ALL tools, then returns a random response or `custom_output_text`
- Best for: testing that tools are reachable and return something
- Usage: `Agent(TestModel(), tools=[...], deps_type=ChatDeps)`

**`FunctionModel`** (`from pydantic_ai.models.function import FunctionModel, DeltaToolCall, DeltaThinkingPart`):
- Constructor: `FunctionModel(function=None, *, stream_function=None)`
- `stream_function: AsyncIterator[str | dict[int, DeltaToolCall] | dict[int, DeltaThinkingPart]]`
  - Yield `str` for text content chunks
  - Yield `{index: DeltaToolCall(name=..., json_args=..., tool_call_id=...)}` for tool calls
  - Yield `{index: DeltaThinkingPart(content=...)}` for thinking
- Best for: deterministic stream replay (the Phase 4.4 `MockLLMStream` scenarios)

**Anti-pattern from CONTEXT.md:** "Don't mock at Agent level when you could mock at Model level." Phase 5 should use `FunctionModel(stream_function=...)` inside `_MockLLMProvider.build_agent()` so the real PydanticAI streaming code path runs in tests.

**Planner rule for D-17 mock rewrite:**
```python
from pydantic_ai.models.function import FunctionModel, DeltaToolCall, DeltaThinkingPart
from pydantic_ai import Agent, RunContext

async def greeting_stream(messages, agent_info):
    yield "Hello! "
    yield "How can I help you plan your trip today?"

async def single_tool_call_stream(messages, agent_info):
    yield {0: DeltaToolCall(name="search_flights", json_args='{"origin":"LAX","destination":"JFK","departure_date":"2026-06-15","passengers":1}', tool_call_id="call_test")}
    # Second call (after tool result comes back):
    yield "I found 5 flights from LAX to JFK."

# In _MockLLMProvider.build_agent():
model = FunctionModel(stream_function=self._stream_func)
return Agent(model, tools=list(tools), deps_type=deps_type)
```

---

### For Ollama: native PydanticAI Ollama support vs `OpenAIChatModel`?

**Verdict: Use `OpenAIChatModel` with `OllamaProvider`.** There is NO `OllamaModel` in `pydantic_ai.models.ollama` (the module does not exist). [VERIFIED: pydantic-ai 0.8.1 source]

```python
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.ollama import OllamaProvider

model = OpenAIChatModel(
    "qwen3:4b",
    provider=OllamaProvider(base_url="http://localhost:11434/v1"),
)
```

`OllamaProvider` is a `Provider[AsyncOpenAI]` that wraps `AsyncOpenAI` with the Ollama base URL. It provides `qwen_model_profile` for qwen models (which inherits `thinking_tags=('<think>', '</think>')`), `deepseek_model_profile`, etc.

The `"ollama"` string prefix in `OpenAIChatModel(model_name, provider="ollama")` also works and resolves to `OllamaProvider(base_url=os.getenv("OLLAMA_BASE_URL"))`. However, since the project already has `Settings.ollama_base_url`, use the explicit provider constructor.

---

### For LM Studio: does the `api_key="lm-studio"` sentinel survive?

**Verdict: Sentinel not needed — PydanticAI auto-sets a placeholder.** [VERIFIED: pydantic-ai 0.8.1 `providers/openai.py`]

When `OpenAIProvider(base_url=..., api_key=None)` and `OPENAI_API_KEY` is not set and `base_url` is provided, PydanticAI auto-sets `api_key = "api-key-not-set"`. The explicit `"lm-studio"` sentinel from Phase 4.5 can be dropped:

```python
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

# For LMStudioProvider.build_agent():
model = OpenAIChatModel(
    self._model,
    provider=OpenAIProvider(base_url=self._base_url),  # api_key auto-set to placeholder
)
```

---

### Tool registration: `@agent.tool` decorator vs `Agent(tools=[...])` constructor?

**Verdict: Use `Agent(tools=[...], deps_type=ChatDeps)` at agent construction per D-07.** [VERIFIED: Agent constructor source]

The `Agent` constructor accepts `tools: Sequence[Tool | ToolFuncEither]`. Regular async functions with `ctx: RunContext[ChatDeps]` as the first parameter are automatically recognized as tool functions taking context.

```python
# search_flights becomes a plain async function (not @tool decorated)
async def search_flights(
    ctx: RunContext[ChatDeps],
    origin: str,
    destination: str,
    departure_date: str,
    ...
) -> str:
    client = ctx.deps.flight_client
    ...

# In LLMProvider.build_agent():
return Agent(model, tools=[search_flights], deps_type=ChatDeps)
```

The `@agent.tool` decorator approach requires a pre-created agent instance — incompatible with the per-session agent construction in D-04/D-07.

---

### `agent.run_stream(...)` vs `agent.iter(...)` — which for ChatService?

**Verdict: Use `agent.iter()` for ChatService.chat_stream().** [VERIFIED: pydantic-ai 0.8.1 source analysis]

`agent.run_stream()`:
- Returns `AsyncContextManager[StreamedRunResult]`
- `StreamedRunResult.stream_text(delta=True)` yields text chunks (no tool events)
- `StreamedRunResult.stream_responses()` yields `(ModelResponse, bool)` snapshots
- Tools are processed silently in `on_complete()` after the context exits
- `result.new_messages()` available after the context exits
- Best for: simple text streaming without needing to observe tool execution

`agent.iter()`:
- Returns `AsyncContextManager[AgentRun]`
- Walk nodes: `UserPromptNode` → `ModelRequestNode` → `CallToolsNode` → `End`
- `ModelRequestNode.stream(ctx)` → iterate `ModelResponseStreamEvent` (PartStart, PartDelta, FinalResult)
- `CallToolsNode.stream(ctx)` → iterate `HandleResponseEvent` (FunctionToolCallEvent, FunctionToolResultEvent)
- `agent_run.result.new_messages()` after `End`
- **Required for ChatService** since it must emit `ToolCallEvent` and `ToolResultEvent` live

---

## Per-Provider Migration Rules

### Ollama Provider

| Property | Value |
|----------|-------|
| PydanticAI class | `pydantic_ai.models.openai.OpenAIChatModel` |
| Provider | `pydantic_ai.providers.ollama.OllamaProvider(base_url=self._base_url)` |
| Constructor | `OpenAIChatModel(self._model, provider=OllamaProvider(base_url=self._base_url))` |
| Thinking surface | Native via `<think>` tag parsing (ModelProfile default). `ThinkingPartDelta.content_delta` for delta events. No special config needed. |
| `validate_config()` | Keep Phase 4.5 implementation — still uses `httpx` to probe `GET {base_url}/api/tags` and check model presence. ProbeError contract unchanged. |
| `list_models()` | Keep Phase 4.5 implementation — `httpx` to `GET {base_url}/api/tags`. |
| `build_agent()` | See code below |

```python
# OllamaProvider.build_agent() — new method replacing bind_tools()
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.ollama import OllamaProvider

def build_agent(self, tools: Sequence[Any], deps_type: type[Any]) -> Agent[Any, str]:
    model = OpenAIChatModel(
        self._model,
        provider=OllamaProvider(base_url=self._base_url),
    )
    return Agent(model, tools=list(tools), deps_type=deps_type)
```

**Drop:** `reasoning=True` flag (no longer needed), `_model_supports_reasoning()` method, `langchain_ollama.ChatOllama` import.

---

### OpenAI Provider

| Property | Value |
|----------|-------|
| PydanticAI class | `OpenAIChatModel` (standard) or `OpenAIResponsesModel` (o-series) |
| Provider | `pydantic_ai.providers.openai.OpenAIProvider(api_key=self._api_key)` |
| Thinking surface | `ThinkingPart` via Responses API only (o-series). Standard models: no ThinkingPart emitted. |
| `validate_config()` | Keep Phase 4.5 key-presence check. No change. |
| `list_models()` | Keep Phase 4.5 curated list. |
| `build_agent()` | Dispatch on model name prefix (D-14): |

```python
from pydantic_ai.models.openai import OpenAIChatModel, OpenAIResponsesModel
from pydantic_ai.providers.openai import OpenAIProvider

_O_SERIES_PREFIXES: tuple[str, ...] = ("o1", "o3")  # from Settings

def build_agent(self, tools: Sequence[Any], deps_type: type[Any]) -> Agent[Any, str]:
    provider = OpenAIProvider(api_key=self._api_key)
    if any(self._model.startswith(p) for p in self._o_series_prefixes):
        model = OpenAIResponsesModel(self._model, provider=provider)
    else:
        model = OpenAIChatModel(self._model, provider=provider)
    return Agent(model, tools=list(tools), deps_type=deps_type)
```

**Note:** `SecretStr` wrapping from Phase 4.5 is not needed — PydanticAI takes plain `str` for `api_key`.

---

### Anthropic Provider

| Property | Value |
|----------|-------|
| PydanticAI class | `pydantic_ai.models.anthropic.AnthropicModel` |
| Provider | `pydantic_ai.providers.anthropic.AnthropicProvider(api_key=self._api_key)` |
| Thinking surface | Native via `BetaThinkingBlock` / `BetaThinkingDelta` — handled automatically when model returns thinking. No special config. |
| `validate_config()` | Keep Phase 4.5 key-presence check. IMPORTANT: `AnthropicProvider(api_key=None)` raises `UserError` — validate_config MUST run before build_agent. |
| `list_models()` | Keep Phase 4.5 curated list. |

```python
from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.providers.anthropic import AnthropicProvider

def build_agent(self, tools: Sequence[Any], deps_type: type[Any]) -> Agent[Any, str]:
    # validate_config() MUST have been called first (same as Phase 4.5 Pitfall 2)
    assert self._api_key is not None  # defense-in-depth
    model = AnthropicModel(
        self._model,
        provider=AnthropicProvider(api_key=self._api_key),
    )
    return Agent(model, tools=list(tools), deps_type=deps_type)
```

---

### LM Studio Provider

| Property | Value |
|----------|-------|
| PydanticAI class | `pydantic_ai.models.openai.OpenAIChatModel` |
| Provider | `pydantic_ai.providers.openai.OpenAIProvider(base_url=self._base_url)` |
| Thinking surface | Best-effort: if the loaded model returns `<think>` tags, they will be parsed by the default `thinking_tags=('<think>', '</think>')`. |
| `validate_config()` | Keep Phase 4.5 httpx probe. No change. |
| `list_models()` | Keep Phase 4.5 `GET {base_url}/models` discovery. |
| `api_key sentinel` | NOT needed — `OpenAIProvider(base_url=..., api_key=None)` auto-sets `"api-key-not-set"` placeholder when `OPENAI_API_KEY` not in env. |

```python
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

def build_agent(self, tools: Sequence[Any], deps_type: type[Any]) -> Agent[Any, str]:
    model = OpenAIChatModel(
        self._model,
        provider=OpenAIProvider(base_url=self._base_url),  # no api_key needed
    )
    return Agent(model, tools=list(tools), deps_type=deps_type)
```

---

## Agent + RunContext + Tool Registration

### `ChatDeps` dataclass (D-05)

```python
from dataclasses import dataclass
from app.tools.flight_client import FlightAPIClient

@dataclass(frozen=True)
class ChatDeps:
    """Per-turn dependency container for PydanticAI RunContext injection."""
    flight_client: FlightAPIClient
    session_id: str
    user_id: str
```

### `search_flights` signature with `RunContext[ChatDeps]` (D-06)

The LangChain `@tool` decorator is removed. The function becomes a plain async function:

```python
from pydantic_ai import RunContext
from app.chat.deps import ChatDeps  # or wherever ChatDeps lives

async def search_flights(
    ctx: RunContext[ChatDeps],
    origin: str,
    destination: str,
    departure_date: str,
    passengers: int = 1,
    sort_by: str = "price",
    max_price: float | None = None,
    max_duration: int | None = None,
    max_stops: int | None = None,
    limit: int = 5,
) -> str:
    """[docstring preserved — PydanticAI uses it for tool description]"""
    client = ctx.deps.flight_client  # replaces getattr(search_flights, "_flight_client", None)
    if client is None:
        return "Error: Flight search service not initialized."
    ...  # rest of body unchanged
```

The `getattr(search_flights, "_flight_client", None)` line is deleted.
The `search_flights._flight_client = flight_client` line in `api/main.py::lifespan` is deleted.

### `provider.build_agent(tools, deps_type)` call site (D-07)

```python
# In ChatService.create_session():
agent = provider.build_agent(tools=[search_flights], deps_type=ChatDeps)
self._agents[session_id] = agent
```

### `agent.iter()` and history persistence (D-04, D-08)

```python
# In ChatService.chat_stream():
history = await self._conversation_store.load(session_id)
deps = ChatDeps(
    flight_client=self._flight_client,
    session_id=session_id,
    user_id=self._metadata[session_id]["user_id"],
)
async with self._agents[session_id].iter(
    message,
    message_history=history,
    deps=deps,
) as agent_run:
    async for node in agent_run:
        ...  # yield StreamEvent subclasses from node streams

if agent_run.result is not None:
    new_msgs = agent_run.result.new_messages()
    await self._conversation_store.append(session_id, new_msgs)
```

**`new_messages()` returns** only the messages produced in this run (not the history passed in), so append-only semantics work correctly.

---

## StreamEvent ABC Refactor

### OQ-01 Resolution: Use `BaseModel + ABC` cleanly

```python
# backend/app/chat/models.py  — replaces the Annotated alias

from pydantic import BaseModel, Field
from abc import ABC
from typing import Any, Literal

class StreamEvent(BaseModel, ABC):
    """Base class for all SSE stream events.

    Concrete subclasses keep their ``type: Literal[...]`` discriminator fields
    for SSE wire compatibility. The frontend switch-narrows on ``event.type``
    — unchanged.
    """
    type: str
    session_id: str

class ContentEvent(StreamEvent):
    type: Literal["content"] = "content"
    chunk: str = ""

class ThinkingEvent(StreamEvent):
    type: Literal["thinking"] = "thinking"
    chunk: str = ""

class ToolCallEvent(StreamEvent):
    type: Literal["tool_call"] = "tool_call"
    tool_name: str
    tool_args: dict[str, Any]

class ToolResultEvent(StreamEvent):
    type: Literal["tool_result"] = "tool_result"
    tool_name: str
    tool_result: str
    elapsed_ms: int

class ErrorEvent(StreamEvent):
    type: Literal["error"] = "error"
    error_code: ErrorCode
    message: str
    retryable: bool
    tool_name: str | None = None
    raw_detail: str | None = None

# The old Annotated alias is RETIRED.
# For type annotations that previously used StreamEvent as the union type,
# replace with: ContentEvent | ThinkingEvent | ToolCallEvent | ToolResultEvent | ErrorEvent
# For isinstance checks, use: isinstance(event, StreamEvent)
```

**Wire format:** unchanged. `model_dump_json()` produces identical output to the Phase 4.7 models because the field names and types are identical. [VERIFIED: live test]

**mypy strict:** `ABC` as a mixin with `BaseModel` is clean under mypy. The `type: str` base field is narrowed by `Literal[...]` in subclasses — mypy strict accepts this.

---

## MockLLMStream Strategy

**Verdict: Use `FunctionModel(stream_function=...)` — mock at Model level, not Agent level.** [VERIFIED: pydantic-ai 0.8.1 `models/function.py`]

`FunctionModel` has a `stream_function` that receives `(messages: list[ModelMessage], agent_info: AgentInfo)` and returns `AsyncIterator[str | dict[int, DeltaToolCall] | dict[int, DeltaThinkingPart]]`.

This is superior to mocking at Agent level because:
1. The real PydanticAI `Agent.iter()` code path runs in tests (tool execution, node iteration, history appending).
2. `RunContext[ChatDeps]` is properly constructed and passed to `search_flights`.
3. `agent_run.result.new_messages()` produces real `ModelMessage` objects.

### Recommended `_MockLLMProvider` rewrite (D-17/D-18)

```python
from pydantic_ai.models.function import FunctionModel, DeltaToolCall, DeltaThinkingPart
from pydantic_ai.messages import ModelMessage
from pydantic_ai.tools import RunContext
from pydantic_ai import Agent
import json
from collections.abc import AsyncIterator
from typing import Any

# Chunk types (preserve Phase 4.4 public API)
@dataclass(frozen=True, slots=True)
class Content:
    text: str

@dataclass(frozen=True, slots=True)
class Thinking:
    text: str

@dataclass(frozen=True, slots=True)
class ToolCall:
    name: str
    args: dict[str, Any]
    id: str = "call_test"

Chunk = Content | Thinking | ToolCall

def _make_stream_function(streams: list[list[Chunk]]) -> ...:
    """Return a stream_function that replays pre-baked Chunk sequences."""
    streams_iter = iter(streams)

    async def stream_function(
        messages: list[ModelMessage], agent_info: Any
    ) -> AsyncIterator[str | dict[int, DeltaToolCall] | dict[int, DeltaThinkingPart]]:
        try:
            chunks = next(streams_iter)
        except StopIteration:
            raise RuntimeError("MockLLMStream exhausted") from None
        for chunk in chunks:
            match chunk:
                case Content(text=t):
                    yield t
                case Thinking(text=t):
                    yield {0: DeltaThinkingPart(content=t)}
                case ToolCall(name=n, args=a, id=i):
                    yield {0: DeltaToolCall(name=n, json_args=json.dumps(a), tool_call_id=i)}

    return stream_function


class _MockLLMProvider(LLMProvider):
    """ABC-conforming mock provider for Phase 5 tests."""

    def __init__(self, streams: list[list[Chunk]]) -> None:
        self._streams = streams

    def get_provider_name(self) -> str:
        return "ollama"

    async def validate_config(self) -> ProbeError | None:
        return None

    async def list_models(self) -> list[str]:
        return []

    def build_agent(
        self, tools: Sequence[Any], deps_type: type[Any]
    ) -> Agent[Any, str]:
        model = FunctionModel(stream_function=_make_stream_function(self._streams))
        return Agent(model, tools=list(tools), deps_type=deps_type)
```

**Phase 4.4 locked scenarios (D-17 — must preserve):**

```python
class MockLLMStream:
    @classmethod
    def greeting(cls) -> list[list[Chunk]]:
        return [[Content("Hello! "), Content("How can I help you plan your trip today?")]]

    @classmethod
    def single_tool_call(cls, ...) -> list[list[Chunk]]:
        # NOTE: FunctionModel replays the stream_function on EACH call
        # The tool-call scenario needs TWO stream_function calls:
        # 1st: yields ToolCall chunk → PydanticAI executes the tool
        # 2nd: yields Content chunk (summary)
        return [
            [ToolCall(name="search_flights", args={...}, id="call_test")],
            [Content("I found 5 flights from LAX to JFK.")],
        ]

    @classmethod
    def multi_turn(cls) -> list[list[Chunk]]:
        return [[Content("Based on your earlier query, "), Content("here are more options.")]]
```

**`make_chat_service_with_mock_llm` signature (D-18 — unchanged):**
```python
def make_chat_service_with_mock_llm(streams: list[list[Chunk]]) -> ChatService:
    provider = _MockLLMProvider(streams)
    factory = MagicMock(spec=LLMProviderFactory)
    factory.build = MagicMock(return_value=provider)
    return ChatService(
        flight_client=MockFlightAPIClient(seed=42),
        factory=factory,
        conversation_store=InMemoryConversationStore(),
    )
```

**FunctionModel multi-turn caveat:** `FunctionModel` creates a new `stream_function` call for each `agent.iter()` turn. In the `single_tool_call` scenario, PydanticAI makes two model requests (first for the initial response with tool call, second after tool execution for the summary). The `streams_iter` must have two inner lists. The `multi_turn` scenario only needs one inner list per `chat_stream()` call.

---

## Architecture Patterns

### Recommended File Layout (Claude's Discretion resolution)

Rename `app/llm/protocol.py` → `app/llm/base.py`. Rationale: the file now contains an ABC (`LLMProvider(ABC)`), not a `Protocol`. The name `base.py` is the Python convention for ABC base classes.

```
backend/app/
├── chat/
│   ├── deps.py          # NEW: ChatDeps dataclass
│   ├── models.py        # StreamEvent ABC + 5 concrete subclasses + DTOs
│   ├── service.py       # ChatService rewritten against PydanticAI
│   └── store.py         # NEW: ConversationStore(ABC) + InMemoryConversationStore
├── llm/
│   ├── base.py          # RENAMED from protocol.py: LLMProvider(ABC)
│   ├── errors.py        # ProbeError + ProbeErrorCode (UNCHANGED)
│   ├── factory.py       # LLMProviderFactory (return type annotation changes)
│   ├── log_scrubbing.py # (UNCHANGED)
│   └── providers/
│       ├── ollama.py    # Reshaped: OpenAIChatModel + OllamaProvider
│       ├── openai.py    # Reshaped: OpenAIChatModel / OpenAIResponsesModel
│       ├── anthropic.py # Reshaped: AnthropicModel + AnthropicProvider
│       └── lmstudio.py  # Reshaped: OpenAIChatModel + OpenAIProvider (no sentinel)
├── tools/
│   └── flight_search.py # search_flights gains ctx: RunContext[ChatDeps]; @tool removed
└── api/
    └── main.py          # lifespan: add InMemoryConversationStore; remove _flight_client injection
```

### `ConversationStore` ABC (D-08)

```python
# backend/app/chat/store.py
from abc import ABC, abstractmethod
from pydantic_ai.messages import ModelMessage

class ConversationStore(ABC):
    @abstractmethod
    async def append(self, session_id: str, messages: list[ModelMessage]) -> None: ...
    @abstractmethod
    async def load(self, session_id: str) -> list[ModelMessage]: ...
    @abstractmethod
    async def delete(self, session_id: str) -> None: ...
    @abstractmethod
    async def list_for_user(self, user_id: str) -> list[ConversationInfo]: ...


class InMemoryConversationStore(ConversationStore):
    def __init__(self) -> None:
        self._store: dict[str, list[ModelMessage]] = {}
        self._user_sessions: dict[str, set[str]] = {}  # user_id -> set of session_ids

    async def append(self, session_id: str, messages: list[ModelMessage]) -> None:
        existing = self._store.get(session_id, [])
        self._store[session_id] = existing + messages

    async def load(self, session_id: str) -> list[ModelMessage]:
        return list(self._store.get(session_id, []))

    async def delete(self, session_id: str) -> None:
        self._store.pop(session_id, None)

    async def list_for_user(self, user_id: str) -> list[ConversationInfo]:
        ...  # iterate _user_sessions[user_id], look up metadata on ChatService
```

**`cleanup_expired_sessions` must become `async def`** because it calls `await store.delete(session_id)`. [ASSUMED — based on ABC method signature; trivially enforced]

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| `<think>` tag parsing for Ollama | Manual `<think>...</think>` substring split | PydanticAI's `ModelProfile.thinking_tags` + `handle_text_delta` | Auto-handled via OllamaProvider's model profile; streaming-safe accumulation |
| Tool dependency injection | `search_flights._flight_client = ...` attribute injection | `RunContext[ChatDeps]` | Framework-managed; type-safe; no monkey-patching |
| Two-tier provider shape | Keep `BoundProvider` Protocol | Collapse to single `LLMProvider(ABC)` | PydanticAI's `Agent` IS the tool-bound thing |
| Mock LLM at Agent level | Fake `_MockAgent` that mimics `Agent.run_stream` | `FunctionModel(stream_function=...)` | Preserves real PydanticAI code path in tests |
| Manual `SecretStr` wrapping | `SecretStr(self._api_key)` for PydanticAI providers | Plain `str` | PydanticAI providers accept plain `str` |
| O-series reasoning flag | `reasoning=True` style config | `OpenAIResponsesModel` (Responses API) | Correct architectural separation: Chat Completions vs Responses API |

---

## Common Pitfalls

### Pitfall 1: `run_stream` does not expose tool call events live

**What goes wrong:** Using `async with agent.run_stream(...) as result: async for text in result.stream_text(...)` and expecting `ToolCallEvent`/`ToolResultEvent` to be emitted during streaming. They won't be — tools execute in `on_complete()` AFTER the stream context exits.

**Why it happens:** `run_stream` is designed for text streaming to a UI. Tool execution is handled internally.

**How to avoid:** Use `agent.iter()` for any chat_stream loop that needs to yield tool events live.

---

### Pitfall 2: `ModelMessagesTypeAdapter` import path

**What goes wrong:** `from pydantic_ai import ModelMessagesTypeAdapter` raises `ImportError`.

**Why it happens:** `ModelMessagesTypeAdapter` is NOT exported from `pydantic_ai.__init__`.

**How to avoid:** `from pydantic_ai.messages import ModelMessagesTypeAdapter`.

---

### Pitfall 3: `ToolCallPart.args` may be a `str` (JSON), not `dict`

**What goes wrong:** `tool_args=event.part.args` passed directly to `ToolCallEvent(tool_args=...)` when `tool_args: dict[str, Any]` is expected.

**Why it happens:** `ToolCallPart.args: str | dict[str, Any] | None` — streaming may deliver args as JSON string.

**How to avoid:**
```python
import json
tool_args = (
    event.part.args if isinstance(event.part.args, dict)
    else json.loads(event.part.args or "{}")
)
```

---

### Pitfall 4: `AnthropicProvider(api_key=None)` raises `UserError`

**What goes wrong:** `AnthropicProvider` raises `pydantic_ai.UserError` at construction if `api_key` is `None` and `ANTHROPIC_API_KEY` is not set. This is different from Phase 4.5 where `ChatAnthropic(api_key=None)` raised a Pydantic `ValidationError`.

**How to avoid:** Same pattern as Phase 4.5 — `validate_config()` runs before `build_agent()`. The factory ordering guarantees this. Keep the `assert self._api_key is not None` defense-in-depth guard in `build_agent()`.

---

### Pitfall 5: `OllamaProvider` requires `base_url` (no env-var fallback in tests)

**What goes wrong:** `OllamaProvider()` (no args) raises `UserError: Set the OLLAMA_BASE_URL environment variable` in test environments.

**How to avoid:** Always pass `base_url` explicitly in production and tests. `_MockLLMProvider` does not use `OllamaProvider` at all — it uses `FunctionModel`.

---

### Pitfall 6: `agent.iter()` node types must be checked with `isinstance`, not pattern match

**What goes wrong:** Using `match node: case ModelRequestNode(): ...` fails because `AgentNode` subclasses are dataclasses, not `NamedTuple` or `TypedDict`.

**How to avoid:** Use `isinstance(node, ModelRequestNode)` and `isinstance(node, CallToolsNode)`. PydanticAI also exports `Agent.is_model_request_node(node)` and `Agent.is_call_tools_node(node)` helper methods.

---

### Pitfall 7: `FunctionModel` stream_function is called once per model turn

**What goes wrong:** `single_tool_call` scenario expects two model turns (initial + post-tool), but the `streams_iter` has only one inner list. Second model request raises `RuntimeError: MockLLMStream exhausted`.

**How to avoid:** Each `agent.iter()` call that hits a tool needs TWO `stream_function` invocations (one for the tool-call decision, one for the post-tool summary). `single_tool_call` must return `list[list[Chunk]]` with two inner lists.

---

### Pitfall 8: `pydantic>=2.9.0` floor in pyproject.toml is too low

**What goes wrong:** `pydantic-ai-slim` requires `pydantic>=2.12`. If someone installs in a fresh env, pip might resolve pydantic 2.9.x and fail at import.

**How to avoid:** Bump `pyproject.toml` to `pydantic>=2.12` when adding `pydantic-ai`.

---

### Pitfall 9: `langgraph` is still in pyproject.toml

**What goes wrong:** PR #1 claimed `langgraph` removed but the `langgraph>=1.0.2` entry is still in `pyproject.toml` and the package is installed. Phase 5's `uv remove` must include `langgraph`.

**How to avoid:** Phase 5 Wave 0 / dependency task must include `langgraph` in the removal list.

---

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8.3+ with pytest-asyncio |
| Config file | `backend/pyproject.toml` (`[tool.pytest.ini_options]`, `asyncio_mode = "auto"`) |
| Quick run command | `cd backend && uv run pytest tests/unit/ -x -q` |
| Full suite command | `cd backend && uv run pytest tests/ -q` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| REQ-pydantic-ai-migration | Agent construction per session | unit | `pytest tests/unit/chat/test_service.py::test_create_session -x` | ❌ Wave 0 |
| REQ-pydantic-ai-migration | `chat_stream()` greeting (no tool) | integration | `pytest tests/integration/test_chat_stream.py::test_greeting -x` | ❌ Wave 0 |
| REQ-pydantic-ai-migration | `chat_stream()` single tool call | integration | `pytest tests/integration/test_chat_stream.py::test_single_tool_call -x` | ❌ Wave 0 |
| REQ-pydantic-ai-migration | `chat_stream()` multi-turn | integration | `pytest tests/integration/test_chat_stream.py::test_multi_turn -x` | ❌ Wave 0 |
| REQ-pydantic-ai-migration | RunContext injects FlightAPIClient | unit | `pytest tests/unit/tools/test_flight_search.py::test_runcontext_injection -x` | ❌ Wave 0 |
| REQ-pydantic-ai-migration | OllamaProvider.build_agent() | unit | `pytest tests/unit/llm/test_ollama_provider.py -x` | ❌ Wave 0 |
| REQ-pydantic-ai-migration | ConversationStore ABC + InMemory | unit | `pytest tests/unit/chat/test_store.py -x` | ❌ Wave 0 |
| REQ-pydantic-ai-migration | langchain* absent from imports | unit | `pytest tests/unit/test_no_langchain_imports.py -x` | ❌ Wave 0 |
| REQ-p5-stream-event-abc | `isinstance(e, StreamEvent)` works | unit | `pytest tests/unit/chat/test_models.py::test_streamevent_abc -x` | ❌ Wave 0 |
| REQ-p5-stream-event-abc | Wire format unchanged | unit | `pytest tests/unit/chat/test_models.py::test_wire_format -x` | ❌ Wave 0 |
| D-13 | OllamaProvider ThinkingEvent (gated) | acceptance | `pytest tests/acceptance/test_ollama_thinking.py -x` (requires OLLAMA running, qwen3:4b) | ❌ Wave 0 |

### Wave 0 Gaps
- [ ] `backend/tests/unit/chat/test_service.py` — ChatService unit tests (create_session, chat_stream with mock)
- [ ] `backend/tests/unit/chat/test_store.py` — ConversationStore ABC + InMemory coverage
- [ ] `backend/tests/unit/chat/test_models.py` — StreamEvent ABC + wire format golden test
- [ ] `backend/tests/unit/tools/test_flight_search.py` — RunContext injection test
- [ ] `backend/tests/unit/llm/test_ollama_provider.py` — OllamaProvider.build_agent() test
- [ ] `backend/tests/unit/test_no_langchain_imports.py` — import-scan assertion
- [ ] `backend/tests/integration/test_chat_stream.py` — three locked scenarios (greeting, single_tool_call, multi_turn) via `make_chat_service_with_mock_llm`
- [ ] `backend/tests/acceptance/test_ollama_thinking.py` — gated qwen3:4b acceptance test

*(If existing test infrastructure covers any of these: "None — existing test infrastructure covers all phase requirements")*

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `BaseChatModel.bind_tools()` → `BoundProvider` | `Agent(model, tools=[...], deps_type=...)` | PydanticAI migration | Two-tier shape collapses to one |
| `chunk.additional_kwargs["reasoning_content"]` | `ThinkingPartDelta.content_delta` | PydanticAI migration | Cleaner; works for Anthropic + Ollama |
| `@tool` decorator from `langchain_core.tools` | Plain `async def` with `ctx: RunContext[ChatDeps]` first param | PydanticAI migration | Dependency injection via framework, not monkey-patch |
| `search_flights._flight_client = flight_client` | `ctx.deps.flight_client` in tool body | PydanticAI migration | Closes ARCHITECTURE.md "Monkey-Patched Tool Dependency" anti-pattern |
| `InMemoryChatMessageHistory` | `list[ModelMessage]` in `ConversationStore` | PydanticAI migration | Native PydanticAI type; Phase 6 PostgresConversationStore maps directly |

**Deprecated/outdated after Phase 5:**
- `langchain`, `langchain-core`, `langchain-ollama`, `langchain-openai`, `langchain-anthropic`, `langgraph`: all removed
- `BoundProvider` Protocol: retired
- `LLMProvider` Protocol: converted to ABC
- `ChatOllama` with `reasoning=True`: superseded by OllamaProvider + thinking_tags

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `cleanup_expired_sessions` must become `async def` | Per-Provider Migration / ConversationStore ABC | Trivial — it's a mechanical change forced by `await store.delete()` |
| A2 | `FunctionModel` replays stream_function on each model turn within a single `agent.iter()` call | MockLLMStream Strategy | Medium — if PydanticAI uses a shared stream, the stream_function would need restructuring; verify in Wave 0 tests |
| A3 | Anthropic extended thinking fires automatically when the model returns `BetaThinkingBlock` — no special model settings required | Anthropic Provider | Low — confirmed in source but not tested end-to-end; gated acceptance test (D-13) verifies |
| A4 | `agent_run.result` is populated after the `End` node is iterated | Agent + RunContext section | Low — confirmed in AgentRun.result source; `result` is `None` until `End` is returned |

**If this table has only low-risk items:** All critical claims were verified against installed pydantic-ai 0.8.1 source.

---

## Open Questions / Open Risks

### OQ-R1: `ModelMessagesTypeAdapter` serialization format may change between pydantic-ai minor versions

PydanticAI is in active development (v0.8.x as of 2026-06-03). The `ModelMessage` discriminated union schema could change between minor versions (e.g., new `part_kind` values added, field renames). Phase 6's `PostgresConversationStore` will store serialized messages in a DB column. If the pydantic-ai version is upgraded in Phase 6+, existing stored messages may not deserialize correctly.

**Mitigation:** Store the pydantic-ai version alongside serialized messages in the `Conversation` table. Flag for Phase 6 discussion.

---

### OQ-R2: Anthropic extended thinking may require `betas=["thinking-in-streaming"]` header

The `AnthropicStreamedResponse` in pydantic-ai 0.8.1 handles `BetaThinkingBlock` and `BetaThinkingDelta` from the Anthropic Beta API. Extended thinking is a beta feature. Whether pydantic-ai automatically adds the required `anthropic-beta` header, or whether the caller must configure it, was not verified against a live Anthropic account.

**Mitigation:** The D-13 gated acceptance test will surface this. If the header is required, `AnthropicProvider.build_agent()` may need `model_settings={"extra_headers": {"anthropic-beta": "thinking-in-streaming"}}`.

---

### OQ-R3: `FunctionModel` stream_function interaction with tool execution

The exact sequence of `stream_function` calls when PydanticAI executes a tool via `FunctionModel` has not been tested end-to-end. The analysis is based on source code reading. The Wave 0 `test_single_tool_call` integration test will be the definitive verification.

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| uv | Dep management | ✓ | 0.9.10 | — |
| Python 3.13 | Runtime | ✓ | (project uses 3.13) | — |
| pydantic-ai | Phase 5 | ✗ (not yet installed in project) | 0.8.1 on PyPI | — |
| Ollama daemon | D-13 acceptance test | ✗ (not verified) | — | Test gated with `@pytest.mark.skipif` |
| OpenAI API key | D-13 acceptance test | ✗ (not verified) | — | Test gated on `OPENAI_API_KEY` env |
| Anthropic API key | D-13 acceptance test | ✗ (not verified) | — | Test gated on `ANTHROPIC_API_KEY` env |

**Missing dependencies with no fallback:** None — pydantic-ai installs via `uv add`.

**Missing dependencies with fallback:** All cloud/local LLM acceptance tests are gated with `@pytest.mark.skipif`.

---

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | Not touched by this phase |
| V3 Session Management | yes | Per-session `Agent[ChatDeps, str]` replaces `BoundProvider`; session lifecycle unchanged |
| V4 Access Control | no | `get_current_active_user` dependency unchanged |
| V5 Input Validation | yes | Tool input validation unchanged (FlightQuery validators from Phase 4.8) |
| V6 Cryptography | no | JWT/password hashing unchanged |

### Known Threat Patterns for PydanticAI stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| API key leakage in logs | Info Disclosure | `_scrub` from `app.llm.log_scrubbing` preserved; pydantic-ai providers take plain `str` not `SecretStr` — ensure api_key not logged at INFO level |
| Prompt injection via tool results | Tampering | `ToolReturnPart.content` passed as `str(ret.content)` to LLM context; PydanticAI constructs the system context internally |
| `_flight_client` removal | Reduces attack surface | Closes "Monkey-Patched Tool Dependency" anti-pattern |

---

## Sources

### Primary (HIGH confidence)
- pydantic-ai 0.8.1 source (installed to `/tmp/pai_src`): `agent.py`, `_agent_graph.py`, `result.py`, `messages.py`, `models/openai.py`, `models/anthropic.py`, `models/function.py`, `models/test.py`, `providers/ollama.py`, `providers/openai.py`, `providers/anthropic.py`, `_thinking_part.py`, `_parts_manager.py`, `_run_context.py`
- PyPI metadata for `pydantic-ai` 0.8.1 and `pydantic-ai-slim` 0.8.1 (confirmed authors: Samuel Colvin + pydantic.dev team, github.com/pydantic/pydantic-ai)
- Live Python 3.9 execution: OQ-01 (`BaseModel + ABC + discriminator`), OQ-05 (`ModelMessagesTypeAdapter` round-trip)
- slopcheck 0.6.1: pydantic-ai verdict `[OK]`

### Secondary (MEDIUM confidence)
- pydantic.dev/docs/ai official docs (WebFetch): confirmed `run_stream` as async context manager, `stream_events` API surface, `ModelMessagesTypeAdapter` usage pattern, `OllamaModel` vs `OpenAIChatModel+OllamaProvider`
- Installed project packages: langchain 0.3+, langchain-ollama 1.0.0, pydantic 2.12.3 (confirmed compatible floor)

### Tertiary (LOW confidence)
- None — all claims verified against primary sources

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — version confirmed on PyPI, source inspected
- Architecture (stream loop): HIGH — `agent.iter()` pattern verified against installed source
- OQ-01 through OQ-05: HIGH — verified by live execution or source inspection
- Pitfalls: HIGH — sourced from source analysis of pydantic-ai 0.8.1
- Mock strategy: MEDIUM — FunctionModel analysis is source-reading; Wave 0 test confirms

**Research date:** 2026-06-03
**Valid until:** 2026-08-01 (pydantic-ai is pre-1.0 and changes frequently; re-verify before execution if more than 2 weeks pass)

---

## RESEARCH COMPLETE
