# Phase 5: PydanticAI Migration - Context

**Gathered:** 2026-06-02
**Status:** Ready for planning

<domain>
## Phase Boundary

Replace LangChain `bind_tools()` with PydanticAI `Agent` inside `ChatService`. The frontend-facing SSE event contract from Phase 4.7 (`ContentEvent | ThinkingEvent | ToolCallEvent | ToolResultEvent | ErrorEvent`) is preserved unchanged — internal extraction is rewritten against PydanticAI's stream surface.

Convert `LLMProvider`/`BoundProvider` from `typing.Protocol` to `abc.ABC` (project rule per `/dignified-python`); the two-tier shape collapses into a single ABC because PydanticAI's `Agent` IS the tool-bound thing (no second tier needed). Reshape all four providers (Ollama, OpenAI, Anthropic, LM Studio) around PydanticAI `Model` + `Agent`. Refactor `StreamEvent` discriminated-union alias into a proper `StreamEvent(ABC)` hierarchy (REQ-p5-stream-event-abc bundled in because the producer is being rewritten anyway).

Replace the `search_flights._flight_client` attribute back-door with PydanticAI's `RunContext[Deps]` mechanism. Drop `langchain`, `langchain-core`, `langchain-ollama`, `langchain-openai`, `langchain-anthropic` from `pyproject.toml`; add `pydantic-ai`. Update `MockLLMStream` (Phase 4.4) to drive the new agent surface. ADR-001 transitions Locked → Superseded; ADR-007 (PydanticAI) becomes Locked.

**Resequenced 2026-06-02 (PR #20 review):** PydanticAI lands BEFORE the Phase 6 Postgres re-platform. The conversation history representation chosen here (Decision D-08) directly shapes Phase 6's `Message` SQLModel — that's the whole point of the resequence.

**In scope:**
- Provider ABC layer: single `LLMProvider(ABC)` with `build_agent(tools, deps_type) -> Agent`. `BoundProvider` retires.
- Four concrete providers reshaped against `pydantic_ai.models.{OpenAIModel, AnthropicModel, OllamaModel/OpenAIModel-with-base-url}`.
- `LLMProviderFactory.build()` returns the concrete provider; ChatService calls `provider.build_agent(...)` per session.
- `ChatDeps` frozen dataclass (`flight_client` + `session_id` + `user_id`) wired through `RunContext`.
- `search_flights` signature gains `ctx: RunContext[ChatDeps]` as first parameter; reads `ctx.deps.flight_client`.
- `ConversationStore(ABC)` + `InMemoryConversationStore` replacing `_histories: dict[str, InMemoryChatMessageHistory]`. Phase 6 swaps in `PostgresConversationStore`.
- ChatService rewires: `chat_stream()` consumes `agent.run_stream(...)` events; per-provider stream loop maps `ThinkingPart`/`ThinkingPartDelta` to `ThinkingEvent`, `TextPart`/`TextPartDelta` to `ContentEvent`, tool events to `ToolCallEvent`/`ToolResultEvent`, exceptions to `ErrorEvent`.
- `StreamEvent(ABC)` base class with five concrete subclasses (refactor of today's discriminated-union alias).
- `MockLLMStream` (and `_MockLLMProvider`/`_MockBoundProvider` adapters) updated for the new surface; default `pytest` stays fast and offline.
- `langchain*` removed from `pyproject.toml`; `pydantic-ai` added; `uv lock` reflects the swap.
- ADR transitions: ADR-001 → Superseded; ADR-007 → Locked.

**Out of scope (deferred):**
- Postgres-backed conversation store → Phase 6 (`PostgresConversationStore` swaps in via DI).
- `Message` SQLModel definition → Phase 6.
- `_flight_client` FastAPI `Depends(get_flight_client)` for the residual route plumbing → Phase 6 (`REQ-p5-flight-client-di` may already be closed by this phase's RunContext rewire — confirm at plan time).
- Cloud reasoning-billing observability (token counts on extended thinking) → out of scope; v1.5 doesn't surface usage telemetry.
- DSPy / GraphQL / hotel-or-restaurant tools → v2.

</domain>

<decisions>
## Implementation Decisions

### Provider Abstraction Shape

- **D-01: Single `LLMProvider(ABC)` with `build_agent(tools, deps_type) -> Agent`. `BoundProvider` retires.**
  PydanticAI's `Agent` IS the tool-bound thing — there's no second tier. The two-tier `LLMProvider → BoundProvider` shape from Phase 4.5 collapses. The Phase 4.5 rationale ("`bind_tools` returns `Runnable`, not `BaseChatModel`") was LangChain-specific; it doesn't apply to PydanticAI.

- **D-02: ABC surface:** `get_provider_name()`, `validate_config()` (returns `ProbeError | None`), `list_models()`, `build_agent(tools: Sequence, deps_type: type[Deps]) -> Agent[Deps, str]`.
  `validate_config` keeps the Phase 4.5 contract — same `ProbeError`/`ProbeErrorCode` taxonomy on the wire (frontend `mapProbeError` is unchanged). `list_models` keeps the Phase 4.5 D-04 / D-07 split (local providers hit the daemon, cloud providers return curated lists).

- **D-03: ABC, not Protocol — closes the ARCHITECTURE.md "Known Tech Debt" entry.**
  Per `/dignified-python` skill: ABC is the project convention for interfaces concrete implementations must satisfy. `@runtime_checkable Protocol` is reserved for third-party duck-typing only. Concrete provider classes explicitly subclass `LLMProvider`.

- **D-04: `LLMProviderFactory.build()` returns the concrete `LLMProvider`; ChatService calls `provider.build_agent(...)` per session.**
  Factory's `match` block on `config.provider` stays; only the return type annotation changes. `ChatService.create_session` now calls `provider.validate_config()` then `provider.build_agent(tools=[search_flights], deps_type=ChatDeps)` and stores the resulting `Agent[ChatDeps, str]` keyed by `session_id`. The Phase 4.5 `_bound_providers` dict becomes `_agents: dict[str, Agent[ChatDeps, str]]`.

### Tool DI via RunContext

- **D-05: `ChatDeps` frozen dataclass: `flight_client: FlightAPIClient`, `session_id: str`, `user_id: str`.**
  More than minimal because Phase 8 structured logging will want `request_id`/`session_id`/`user_id` correlation — adding the fields now is cheap and avoids a Deps-shape churn later. Not full-context (no `Settings`) — that's an over-broad dep that opens the door to settings-driven tool behavior we don't need yet (YAGNI). Frozen per `~/.claude/rules/python/coding-style.md`.

- **D-06: `search_flights` gains `ctx: RunContext[ChatDeps]` as first parameter.**
  ```python
  async def search_flights(
      ctx: RunContext[ChatDeps],
      origin: str, destination: str, departure_date: str, ...
  ) -> str:
      client = ctx.deps.flight_client
      ...
  ```
  Replaces today's `search_flights._flight_client` attribute back-door (closes the ARCHITECTURE.md "Monkey-Patched Tool Dependency" anti-pattern). The function is called only by the LLM and by tests — blast radius is the registration site + a handful of test imports. Per `RunContext[ChatDeps]`-typed signature is required so PydanticAI passes the right `Deps` shape.

- **D-07: Tool registration via `Agent(model, tools=[search_flights], deps_type=ChatDeps)` at agent construction; `Agent.run_stream(..., deps=ChatDeps(...))` per turn.**
  `ChatService.chat_stream` constructs the per-turn `ChatDeps` (pulling `flight_client` from constructor injection, `session_id` from the call, `user_id` from session metadata) and passes it to `agent.run_stream(..., deps=...)`. PydanticAI threads it into every tool call.

### Conversation History Shape

- **D-08: `ConversationStore(ABC)` with `InMemoryConversationStore` impl in Phase 5; `PostgresConversationStore` swaps in via DI in Phase 6.**
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
  `ChatService` depends on the ABC; Phase 6 just registers a different concrete in `lifespan`. Phase 6's `Message` SQLModel maps onto `ModelMessage` shape directly (no JSON-payload escape hatch needed).

- **D-09: `_metadata` and `_last_activity` dicts stay on ChatService (per-session lifecycle state, not conversation content).**
  These are runtime-only ephemera; they don't need a store abstraction. Phase 6 may fold `created_at` / `last_activity` into the `Conversation` SQLModel — that's a Phase 6 decision, not Phase 5's.

- **D-10: Existing `_bound_providers: dict[str, BoundProvider]` becomes `_agents: dict[str, Agent[ChatDeps, str]]`.**
  Same per-session lifecycle as today's bound providers. Agents are constructed in `create_session` after `validate_config` succeeds. `chat_stream` reads from this dict.

- **D-11: Storage format inside `InMemoryConversationStore` is `list[ModelMessage]` (PydanticAI's native shape).**
  No serialization at the in-memory boundary. Phase 6's `PostgresConversationStore` will JSON-serialize via PydanticAI's `ModelMessagesTypeAdapter` for DB columns — that's a Phase 6 implementation detail.

### Thinking/Reasoning Extraction

- **D-12: All four providers emit `ThinkingEvent` on a best-effort basis — wherever PydanticAI surfaces `ThinkingPart`/`ThinkingPartDelta` events, the stream loop maps them to `ThinkingEvent`.**
  Models that don't emit reasoning (small Ollama models, gpt-4o-mini, claude haiku) silently emit no `ThinkingEvent` — silent absence, not a feature gap. Frontend rendering is unchanged: the existing `ThinkingCard` only appears when `ThinkingEvent` arrives.

- **D-13: Per-provider acceptance test confirms the flow works when the model supports it.**
  Mirrors the Phase 4.5 gated-cloud-acceptance-tests pattern (`@pytest.mark.skipif(not env_var, ...)`):
  - Ollama: qwen3:4b, gated on local Ollama daemon.
  - OpenAI: o-series (e.g. `o3-mini`), gated on `OPENAI_API_KEY` + flag.
  - Anthropic: extended-thinking model (e.g. `claude-3-7-sonnet`), gated on `ANTHROPIC_API_KEY` + flag.
  - LM Studio: best-effort; if the loaded model emits reasoning tokens via OpenAI-compat surface, it works; otherwise no test.

- **D-14: OpenAI o-series reasoning requires `OpenAIResponsesModel` (different code path than `OpenAIChatModel`).**
  `OpenAIProvider.build_agent` dispatches: if the selected model is in a known reasoning-model list (`o1`, `o1-mini`, `o3`, `o3-mini`, …) use `OpenAIResponsesModel`; otherwise `OpenAIChatModel`. The reasoning-model list lives on `Settings` (per CLAUDE.md "tunable thresholds live on Settings") — open to a curated module-level set if researcher confirms PydanticAI exposes a helper.

### StreamEvent ABC Refactor

- **D-15: `StreamEvent` becomes a proper `class StreamEvent(BaseModel, ABC)` base class with `ContentEvent`/`ThinkingEvent`/`ToolCallEvent`/`ToolResultEvent`/`ErrorEvent` as concrete subclasses.**
  Each subclass keeps its `type: Literal[...]` discriminator field for SSE wire compatibility — the frontend keeps switch-narrowing by `event.type`. The `Annotated[..., Field(discriminator="type")]` union alias from Phase 4.7 retires; consumers reference `StreamEvent` directly. Pydantic v2 supports ABC + discriminator together (researcher confirms; if not, fallback is `Union` over the concrete subclasses without the ABC layer — see Open Question OQ-01).

- **D-16: REQ-p5-stream-event-abc is bundled into Phase 5 because the producer (`ChatService.chat_stream`) is being rewritten anyway.**
  No separate plan for the ABC refactor — it lands in the same change as the LangChain → PydanticAI rewrite.

### Test Strategy

- **D-17: `MockLLMStream` (Phase 4.4) is updated to drive PydanticAI's agent surface.**
  Today's `MockLLM(BaseChatModel)` subclass is LangChain-specific. The new mock provides a `_MockLLMProvider` that returns a `_MockAgent` exposing `run_stream` yielding pre-baked PydanticAI `ModelResponseStreamEvent` objects. Same three locked scenarios from Phase 4.4 (`greeting`, `single_tool_call`, `multi_turn`) preserved.

- **D-18: `make_chat_service_with_mock_llm()` factory function from `tests/fixtures/llm.py` keeps its signature; internals rewritten.**
  Tests that use the factory don't need to change. The mock factory now wraps the mock provider with a `MagicMock(spec=LLMProviderFactory)` whose `.build()` returns the mock provider — same shape as today.

- **D-19: Default `pytest` (unit + integration via path discovery) stays fast and offline; gated cloud tests stay gated.**
  No regressions on the Phase 4.5 testing posture.

### Dependency Swap

- **D-20: `pyproject.toml` removes `langchain`, `langchain-core`, `langchain-ollama`, `langchain-openai`, `langchain-anthropic`. Adds `pydantic-ai`.**
  `langgraph` was already removed in PR #1. After the swap, only `pydantic-ai` (and its transitive deps) remain on the LLM client side. `httpx` stays for `validate_config`/`list_models` HTTP probes (until Phase 7's `pyreqwest` swap for the real travel API).

- **D-21: ADR-001 transitions Locked → Superseded; ADR-007 (PydanticAI) becomes Locked. ARCHITECTURE.md updated in the same change.**
  ADR text adjustments included in the Phase 5 plan's Wave-N "docs" plan; `.planning/PROJECT.md` Key Decisions table reflects the transitions.

### Claude's Discretion

- File layout under `backend/app/llm/`: `protocol.py` may rename to `base.py` (since it's now an ABC, not a Protocol). Researcher confirms the convention.
- Concrete provider class internals — which `pydantic_ai.models.*` class wraps which provider; e.g. Ollama may use `OpenAIModel` with a custom `base_url` (PydanticAI native pattern) rather than a dedicated `OllamaModel`. LM Studio likely follows the same OpenAI-compat path it already uses (the Phase 4.5 sentinel `api_key="lm-studio"` may or may not survive — researcher confirms).
- Whether to surface `usage` (token counts) on `ContentEvent` for future Phase 8 telemetry — not required by acceptance criteria; planner decides.
- Whether `ConversationStore.delete` exists in the Phase 5 ABC or only `append`/`load`/`list_for_user` (cleanup_expired_sessions today does dict.pop on multiple dicts; need to mirror that on the ABC).
- Naming: `Agent[ChatDeps, str]` — the output type. Phase 5 stays on `str` (text response); Phase 7+ may move to a typed Pydantic output for `search_flights`. Out of scope here.

### Open Questions for Researcher

- **OQ-01:** Does Pydantic v2 support `class Foo(BaseModel, ABC)` + `Field(discriminator='type')` together cleanly? Fallback: keep `Union` discriminated alias if ABC + discriminator collide.
- **OQ-02:** PydanticAI's stream event types — confirm exact names (`ThinkingPart` vs `ThinkingPartDelta`, `TextPart` vs `TextPartDelta`, `FunctionToolCallEvent`, `FunctionToolResultEvent`) and their attributes (`content` vs `delta` vs `chunk`).
- **OQ-03:** `OpenAIResponsesModel` availability — confirm it's exported from `pydantic_ai.models.openai` and accepts the same auth shape as `OpenAIChatModel`.
- **OQ-04:** Does PydanticAI provide `qwen3:4b` reasoning-token extraction natively for Ollama (parsing `<think>` tags into `ThinkingPart`), or does it surface raw text and we still need to parse?
- **OQ-05:** `ModelMessagesTypeAdapter` JSON serialization — confirm round-trip stability so Phase 6 can use it for the `Message` SQLModel JSON column.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase scope & requirements
- `.planning/ROADMAP.md` §"Phase 5: PydanticAI Migration" — phase goal + 6 success criteria + backward-compat scope statement
- `.planning/REQUIREMENTS.md` §"Phase 5 — PydanticAI Migration" — `REQ-pydantic-ai-migration` and `REQ-p5-stream-event-abc`
- `.planning/PROJECT.md` §"Active" — phase 5 entries, ADR-001 → Superseded transition note, ADR-007 → Locked

### Prior phase context (decisions to honor)
- `.planning/phases/04.5-llm-provider-abstraction-real-cloud-dynamic-ollama/04.5-CONTEXT.md` — D-01..D-28: the LLMProvider Protocol that Phase 5 converts to ABC; provider lifecycle; discovery cache; API-key precedence (D-08); `validate_config` contract; cloud "Test connection" endpoint
- `.planning/phases/04.7-error-handling-streamevent-hierarchy/04.7-CONTEXT.md` — D-04, D-05: discriminated union shape Phase 5 refactors into a proper ABC hierarchy; `ErrorCode` taxonomy; retry endpoint contract
- `.planning/phases/04.4-mock-chat-in-tests/04.4-CONTEXT.md` — `MockLLMStream` fixture contract Phase 5 updates
- `.planning/phases/04.9-pre-phase-5-prep/` — model split + UserRepository DI groundwork (Phase 5 inherits the new module layout)

### Existing code (MUST read before modifying)
- `backend/app/chat/service.py` — `ChatService.__init__`, `create_session`, `chat_stream`. The full LangChain→PydanticAI rewrite lands here. `_histories`, `_bound_providers`, `_metadata`, `_last_activity` shapes change.
- `backend/app/chat/models.py` — `StreamEvent` discriminated-union alias + 5 concrete event models. ABC refactor lands here.
- `backend/app/chat/__init__.py` — exports list updated when StreamEvent ABC lands.
- `backend/app/llm/protocol.py` — `LLMProvider` + `BoundProvider` Protocols; converted to single `LLMProvider(ABC)` (BoundProvider retires). May rename to `base.py`.
- `backend/app/llm/factory.py` — `LLMProviderFactory.build()` return type annotation; `refresh_local_models` stays.
- `backend/app/llm/providers/ollama.py` — reshape against `pydantic_ai.models.OpenAIModel` (with Ollama base_url) or dedicated PydanticAI Ollama support.
- `backend/app/llm/providers/openai.py` — reshape against `pydantic_ai.models.OpenAIChatModel`; reasoning-model dispatch to `OpenAIResponsesModel`.
- `backend/app/llm/providers/anthropic.py` — reshape against `pydantic_ai.models.AnthropicModel`; extended-thinking surface.
- `backend/app/llm/providers/lmstudio.py` — reshape against `pydantic_ai.models.OpenAIChatModel` with `base_url=http://localhost:1234/v1` and sentinel `api_key="lm-studio"` (or whatever PydanticAI requires).
- `backend/app/tools/flight_search.py` — `search_flights` decorator changes from `langchain_core.tools.tool` to PydanticAI tool registration; signature gains `ctx: RunContext[ChatDeps]`. The `_flight_client` back-door is removed.
- `backend/app/api/main.py` — lifespan: `chat_service = ChatService(flight_client=..., factory=..., conversation_store=InMemoryConversationStore())`; the `search_flights._flight_client = flight_client` line is removed.
- `backend/app/api/routes/routes.py` — `POST /api/chat/retry` endpoint stays; internals call PydanticAI agent. SSE serialization unchanged (`model_dump_json()` works on Pydantic models).
- `backend/tests/fixtures/llm.py` — `MockLLM`, `MockLLMStream`, `_MockLLMProvider`, `_MockBoundProvider`, `make_chat_service_with_mock_llm`. Full rewrite.
- `backend/tests/unit/llm/`, `backend/tests/integration/` — every chat-stream test that constructs a session + reads SSE events.
- `backend/pyproject.toml` — `dependencies` list: remove all `langchain*` packages, add `pydantic-ai`.

### Frontend (no changes required, but verify)
- `frontend/src/lib/parseSSE.ts` — switch-narrows on `event.type`; unchanged
- `frontend/src/hooks/useChat.ts` — discriminated-union event handling; unchanged
- `frontend/src/types/chat.ts` — TS discriminated union; unchanged

### Project skills (use proactively)
- `.claude/skills/fastapi/SKILL.md` — `Annotated[T, Depends(...)]`, async route shape, lifespan singletons via `app.state`
- `/dignified-python` — ABC vs Protocol discipline (D-03 enforcement); modern Python idioms
- `/pydantic-ai-agent-builder` — multi-agent + tool design patterns; PydanticAI Agent + RunContext + tool registration

### Codebase analysis maps (live)
- `.planning/codebase/STACK.md` — current stack baseline (LangChain 0.3+, langchain-* extras). Updated post-Phase-5 to reflect `pydantic-ai`.
- `.planning/codebase/ARCHITECTURE.md` — service layer pattern; lifespan singletons; `app.state` DI registry. Anti-pattern entries "Monkey-Patched Tool Dependency" + "Known Tech Debt: Protocol-vs-ABC" both close at Phase 5.
- `.planning/codebase/TESTING.md` — collaborator-scope taxonomy (unit / integration / e2e); MockLLMStream policy
- `.planning/codebase/CONVENTIONS.md` — `app.state` for singletons; named exports; Pydantic patterns

### Project conventions
- `CLAUDE.md` (project root) — mypy strict, ruff line length 120, "abstract interfaces use ABC, never Protocol", "cross-module taxonomies use StrEnum, not duplicated Literal unions", "tunable thresholds live on Settings"
- `~/.claude/rules/python/coding-style.md` — `@dataclass(frozen=True)` for immutable DTOs (D-05); type annotations on all signatures
- `~/.claude/rules/python/patterns.md` — Protocol for duck typing; the project rule (CLAUDE.md) overrides this for in-project ABCs
- `~/.claude/rules/python/testing.md` — pytest, AAA pattern; the project's path-only test selection (no markers) overrides the marker recommendation

### PydanticAI / SDK references (researcher must verify)
- PydanticAI `Agent[Deps, Output]` — generic agent class; `tools=[...]`, `deps_type=...`, `system_prompt=...` constructor params
- PydanticAI `RunContext[Deps]` — first parameter type for tools that need injected dependencies; exposes `ctx.deps`
- PydanticAI `agent.run_stream(...)` — async-context-managed stream; yields events (`ThinkingPart`, `ThinkingPartDelta`, `TextPart`, `TextPartDelta`, `FunctionToolCallEvent`, `FunctionToolResultEvent`)
- PydanticAI `pydantic_ai.models.openai.OpenAIChatModel` / `OpenAIResponsesModel` — Chat Completions vs Responses API; reasoning-model dispatch
- PydanticAI `pydantic_ai.models.anthropic.AnthropicModel` — Anthropic API; extended-thinking surface
- PydanticAI Ollama support — exact import path + whether qwen3 `<think>` tags parse into `ThinkingPart` natively
- PydanticAI `ModelMessage` and `ModelMessagesTypeAdapter` — message storage shape and JSON round-trip (informs D-08 + D-11)

### Deferred-but-relevant (do NOT implement here)
- ADR-006 (Postgres + Redis + docker-compose) — Phase 6 swaps `InMemoryConversationStore` → `PostgresConversationStore` via DI
- ADR-008 (`pyreqwest`) — Phase 7; outbound HTTP for the real Amadeus client
- ADR-009 (no rate limiting) — applies to all v1 work; nothing in Phase 5 introduces rate limiting

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `app/llm/errors.py` (`ProbeError`, `ProbeErrorCode`) — wire contract preserved verbatim. `validate_config` returns this on the new ABC just like it did on the Protocol.
- `app/llm/factory.py` (`LLMProviderFactory`, `SessionLLMConfig`, `refresh_local_models`) — factory shape preserved; only the return type annotation of `build()` changes.
- `app/chat/models.py` (5 event models + DTOs) — DTOs (`SessionCreateRequest`, `ChatSessionInfo`, `RetryRequest`, etc.) are unchanged; only the `StreamEvent` alias becomes an ABC.
- `app/llm/log_scrubbing.py` (`_scrub`, `install_log_scrubber`) — reused for `ErrorEvent.raw_detail` (Phase 4.7 already wires this; Phase 5 keeps it).
- `app/exceptions.py` (`APIError` hierarchy with `retryable` flag) — used in `chat_stream`'s tool error mapping; preserved.
- `backend/tests/fixtures/llm.py` (`make_chat_service_with_mock_llm` shape) — wrapper signature preserved; internals rewritten (D-17, D-18).
- `backend/tests/fixtures/flights.py` (`create_mock_flight()`) — unchanged.

### Established Patterns
- **Lifespan-managed singletons via `app.state`** — `ChatService`, `LLMProviderFactory`, `provider_models_cache`, `EnvUserRepository` already there; Phase 5 adds `ConversationStore`.
- **Per-session bound state on ChatService** — `_bound_providers` keyed by session_id today; becomes `_agents` in Phase 5.
- **`@dataclass(frozen=True)` for DTOs** — `SessionLLMConfig` follows; `ChatDeps` follows.
- **`match` dispatch on provider name** — `LLMProviderFactory.build` already does this; preserved.
- **DI override** — `app.state` deps overridden in `api/main.py`; same pattern for `get_conversation_store` if planner adds the dependency at route layer (likely not needed; ChatService holds it).
- **StrEnum for cross-module string codes** — `ErrorCode` (Phase 4.7), `ProbeErrorCode` (Phase 4.5); the new ABC subclasses keep `type: Literal[...]` discriminators.
- **Pydantic v2 native discriminated unions** (`Annotated[..., Field(discriminator='type')]`) — Phase 4.7 pattern; Phase 5 absorbs into the ABC base.

### Integration Points
- `api/main.py::lifespan` — construct `InMemoryConversationStore`; pass to `ChatService(...)`. Remove the `search_flights._flight_client = flight_client` line (RunContext replaces it).
- `chat/service.py::ChatService.__init__` — accept `conversation_store: ConversationStore` parameter; replace `_histories` dict with store calls.
- `chat/service.py::ChatService.create_session` — `provider.validate_config()` → `provider.build_agent(tools=[search_flights], deps_type=ChatDeps)` → store agent on `_agents[session_id]` → `await store.append(session_id, [])` for empty history initialization (or lazy-init on first `load`).
- `chat/service.py::ChatService.chat_stream` — full rewrite. Loads history via `await store.load(session_id)`; builds `ChatDeps`; calls `agent.run_stream(message, message_history=history, deps=deps)`; per-event-type maps to `StreamEvent` subclasses; on completion appends `result.new_messages()` via `await store.append(...)`.
- `chat/service.py::ChatService.list_sessions_for_user` — calls `await store.list_for_user(user_id)`.
- `chat/service.py::ChatService.cleanup_expired_sessions` — calls `await store.delete(session_id)` per expired session.
- `tools/flight_search.py::search_flights` — decorator + signature change; internals largely preserved.
- `chat/models.py::StreamEvent` — alias becomes ABC base class; 5 concrete subclasses.
- `tests/fixtures/llm.py` — `MockLLM` / adapters / `MockLLMStream` rewrite for PydanticAI agent surface.
- `tests/unit/`, `tests/integration/` — every chat-stream test updated for the new mock contract.

### Anti-patterns to avoid (project history)
- **Don't keep `search_flights._flight_client` "just in case"** — it must be deleted, not coexist with RunContext. The whole point of D-06 is closing the back-door.
- **Don't ship a `ProtocolProvider` adapter alongside the ABC** — pure rename + retype. No backwards-compat shim.
- **Don't mock at the `Agent` level when you could mock at the `Model` level** — preserves more of the real PydanticAI streaming code path in tests. Mock `_MockLLMProvider.build_agent()` to return an agent with a stub `Model`, not a fully-fake `_MockAgent`. (Researcher confirms: see if PydanticAI exposes a `TestModel`/`FunctionModel` for this.)
- **Don't reshape the SSE wire format** — frontend changes are out of scope. Only `StreamEvent` Python-side moves to an ABC; the JSON-on-the-wire stays identical.

</code_context>

<specifics>
## Specific Ideas

- The `ConversationStore(ABC)` chosen for D-08 is the seam Phase 6's `Message` SQLModel hangs on. The Phase 6 spike (`postgresql+psycopg://` async URI with SQLModel) verifies the persistence layer; the ABC ensures Phase 5 isn't blocked on that.
- LM Studio's `api_key="lm-studio"` sentinel from Phase 4.5 D-16 may or may not survive PydanticAI's OpenAI-compat surface — researcher confirms whether PydanticAI's `OpenAIChatModel` requires a non-empty key field the same way `langchain_openai.ChatOpenAI` did.
- `cleanup_expired_sessions` becomes `async def` because it now calls `await store.delete(...)`. Lifespan shutdown calls it; that path was already async-friendly. Same for any callers in tests.

</specifics>

<deferred>
## Deferred Ideas

- **Postgres-backed conversation store** → Phase 6: `PostgresConversationStore` swaps in via DI. The `Message` SQLModel targets `ModelMessage` shape (D-08 / D-11 ensure this).
- **`Conversation` (vs `session`) renaming** → Phase 6 (`REQ-p5-conversation-rename`). Phase 5 keeps "session" terminology to minimize blast radius; the rename happens once, in the same PR as the Postgres swap.
- **`SessionCreateRequest` SRP split** → Phase 6 (`REQ-p5-session-create-request-split`). Out of scope here.
- **`ProviderInfo` SRP split** → Phase 6 (`REQ-p5-provider-info-split`). Out of scope here.
- **`PostgresUserRepository` + DB seeding** → Phase 6 (`REQ-p5-db-seed`). Phase 5 keeps `EnvUserRepository`.
- **`Depends(get_flight_client)` for residual route plumbing** → Phase 6 (`REQ-p5-flight-client-di`). May be fully closed by D-06's RunContext rewire; confirm at Phase 6 plan time.
- **Token-usage telemetry on `ContentEvent`** → Phase 8 (`REQ-structured-logging`). Out of scope here.
- **Typed Pydantic output for `search_flights`** (`Agent[ChatDeps, FlightSearchResult]`) → Phase 7 territory; the real Amadeus client is the right moment to revisit the output type.
- **`OpenAIResponsesModel` reasoning-token observability** (per-event token counts, reasoning summaries) → Phase 8.
- **Anthropic prompt caching headers** → Phase 8 or v2; explicitly out of v1.5 scope.
- **Multi-agent / agent-as-tool patterns** → not in v1 scope; PydanticAI supports this but the trip planner is a single-agent system.

</deferred>

---

*Phase: 05-pydanticai-migration*
*Context gathered: 2026-06-02*
