# Phase 5: PydanticAI Migration - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-02
**Phase:** 05-pydanticai-migration
**Areas discussed:** Provider abstraction shape, Tool DI via RunContext[Deps], Conversation history shape, Thinking/reasoning extraction

---

## Provider abstraction shape

| Option | Description | Selected |
|--------|-------------|----------|
| A: Single ABC → build_agent() | Collapse to one LLMProvider(ABC) with build_agent(tools, deps_type) -> Agent. No second tier. Provider owns Model construction + Agent wrapping. Factory builds the right provider; ChatService gets an Agent. | ✓ |
| B: Two-tier (renamed) | Keep LLMProvider → BoundAgent two-tier shape. provider.bind_tools(tools) returns an Agent. Largely cosmetic vs A; preserves the existing mental model. | |
| C: Thin — just a Model factory | LLMProvider just builds the pydantic_ai Model. ChatService constructs the Agent itself with model + tools + deps_type. Probe + list_models still on provider but conceptually separable. Most flexibility. | |

**User's choice:** A — Single ABC with `build_agent(tools, deps_type) -> Agent`.
**Notes:** Aligns with PydanticAI's design where `Agent` IS the tool-bound thing — there's no second tier in the framework, so honest modeling collapses the two-tier shape from Phase 4.5. `BoundProvider` retires. The Phase 4.5 rationale ("`bind_tools` returns Runnable, not BaseChatModel") was LangChain-specific.

---

## Tool DI via RunContext[Deps] — Deps shape

| Option | Description | Selected |
|--------|-------------|----------|
| A: Minimal — client only | Just FlightAPIClient. Strict YAGNI. Add session_id/user_id when a tool actually consumes them. Cheapest change today. | |
| B: client + session_id + user_id | FlightAPIClient + session_id + user_id. Cheap to add now; Phase 8 structured logging will want request_id/session_id correlation. Frozen dataclass. | ✓ |
| C: Full context | FlightAPIClient + session_id + user_id + Settings. Opens settings-driven tool behavior. Risk: bigger blast radius on a Settings field rename; tools take an over-broad dep. | |

**User's choice:** B — `ChatDeps(flight_client, session_id, user_id)` as a frozen dataclass.
**Notes:** Adding `session_id` + `user_id` now is cheap and avoids a Deps-shape churn when Phase 8 structured logging lands. Stops short of including `Settings` to avoid an over-broad dep (YAGNI).

---

## Tool DI via RunContext[Deps] — search_flights signature

| Option | Description | Selected |
|--------|-------------|----------|
| Add `ctx: RunContext[ChatDeps]` as first parameter; read `ctx.deps.flight_client` | Explicit RunContext-typed signature. Replaces today's `_flight_client` attribute back-door cleanly. | ✓ |
| Keep parameter-only signature; read client from a closure or module-level lookup | Avoids signature change but rebuilds the back-door we're trying to kill. | |

**User's choice:** Explicit `ctx: RunContext[ChatDeps]` first parameter.
**Notes:** Confirmed as the default after presenting the trade-off; no separate AskUserQuestion needed. Closes the ARCHITECTURE.md "Monkey-Patched Tool Dependency" anti-pattern.

---

## Conversation history shape

| Option | Description | Selected |
|--------|-------------|----------|
| A: Direct dict[str, list[ModelMessage]] | Keep it simple: ChatService stores raw lists. Phase 6 rewrites ChatService internals to use the DB. No premature abstraction. | |
| B: ConversationStore(ABC) with InMemoryConversationStore | Define ConversationStore(ABC) with append/load/list_for_user; ship in-memory impl in Phase 5. Phase 6 swaps in PostgresConversationStore via DI. Cleaner seam; mild over-engineering paid back next phase. | ✓ |
| C: Same shape, just retyped | _histories[session_id] becomes list[ModelMessage]. Phase 6 still has to rewrite the access pattern. | |

**User's choice:** B — `ConversationStore(ABC)` + `InMemoryConversationStore` in Phase 5; Phase 6 swaps in `PostgresConversationStore`.
**Notes:** Phase 6 is the only known consumer, so this is mildly over-engineered today, but the abstraction is paid back immediately in Phase 6 (DI swap, no internal rewrite). Phase 6's `Message` SQLModel maps onto `ModelMessage` via `ModelMessagesTypeAdapter` JSON serialization — that's a Phase 6 detail.

---

## Thinking/reasoning extraction

| Option | Description | Selected |
|--------|-------------|----------|
| A: Best-effort across all providers | Every provider's stream loop maps PydanticAI's ThinkingPart/Delta events to ThinkingEvent. Models that don't emit reasoning silently emit nothing. Acceptance test per provider confirms the flow works when the model supports it. | ✓ |
| B: Ollama-only — preserve today's behavior | Only OllamaProvider emits ThinkingEvent. Cloud reasoning deferred. Smallest behavior delta; avoids cloud-billing surprises from extended thinking. | |
| C: Ollama + Anthropic; OpenAI deferred | Anthropic extended thinking shares the regular streaming surface; OpenAI reasoning needs OpenAIResponsesModel (different code path) — skip to keep scope tight. | |

**User's choice:** A — Best-effort across all four providers.
**Notes:** Frontend rendering is unchanged: ThinkingCard appears only when ThinkingEvent arrives. Per-provider acceptance test (gated on the relevant API key / local daemon) confirms the flow. OpenAI o-series requires `OpenAIResponsesModel` dispatch — researcher confirms exact import path and reasoning-model list (D-14 + OQ-03).

---

## Claude's Discretion

- File naming: `app/llm/protocol.py` → likely `app/llm/base.py` (it's an ABC now, not a Protocol).
- Concrete `pydantic_ai.models.*` choice per provider — researcher confirms whether Ollama uses dedicated PydanticAI Ollama support or `OpenAIChatModel` with a custom base_url.
- Whether `usage` (token counts) is surfaced on `ContentEvent` for future Phase 8 telemetry — planner decides.
- `ConversationStore` ABC method set — must include `delete` to support `cleanup_expired_sessions`; decided in CONTEXT.md D-08 footnote.
- LM Studio sentinel `api_key="lm-studio"` survival depends on whether PydanticAI's `OpenAIChatModel` requires a non-empty key — researcher confirms.

## Deferred Ideas

- **Postgres-backed conversation store** → Phase 6 (`PostgresConversationStore` via DI swap; `Message` SQLModel maps onto `ModelMessage`).
- **`Conversation` (vs `session`) terminology rename** → Phase 6 (`REQ-p5-conversation-rename`).
- **`SessionCreateRequest` SRP split** (target + credentials) → Phase 6 (`REQ-p5-session-create-request-split`).
- **`ProviderInfo` SRP split** (Local vs Cloud subclasses) → Phase 6 (`REQ-p5-provider-info-split`).
- **`PostgresUserRepository` + DB seeding** → Phase 6 (`REQ-p5-db-seed`).
- **`Depends(get_flight_client)` residual route plumbing** → Phase 6 (`REQ-p5-flight-client-di`). May already be closed by D-06's RunContext rewire; confirm at Phase 6 plan time.
- **Token-usage telemetry on `ContentEvent`** → Phase 8 (`REQ-structured-logging`).
- **Typed Pydantic output for `search_flights`** (`Agent[ChatDeps, FlightSearchResult]`) → Phase 7 (real Amadeus client).
- **OpenAIResponsesModel reasoning-token observability** (per-event token counts, reasoning summaries) → Phase 8.
- **Anthropic prompt caching headers** → Phase 8 or v2.
- **Multi-agent / agent-as-tool patterns** → not in v1 scope.
