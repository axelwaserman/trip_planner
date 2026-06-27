---
phase: 05-pydanticai-migration
plan: 04
subsystem: chat
tags: [pydantic-ai, langchain-removal, agent-iter, function-model, conversation-store, run-context, chat-deps, sse-stream-event]

# Dependency graph
requires:
  - phase: 05-pydanticai-migration
    provides: "Wave 0 RED test surface — `tests/unit/chat/test_stream_event_*` + `tests/unit/tools/test_flight_search_no_backdoor.py` (Plan 05-01)"
  - phase: 05-pydanticai-migration
    provides: "Wave 1 foundations — `LLMProvider(ABC)`, `ChatDeps`, `ConversationStore`/`InMemoryConversationStore`, `StreamEvent` ABC refactor (Plan 05-02)"
  - phase: 05-pydanticai-migration
    provides: "Wave 2 providers — concrete `OllamaProvider`/`OpenAIProvider`/`AnthropicProvider`/`LMStudioProvider` returning `pydantic_ai.Agent` from `build_agent` (Plan 05-03)"
provides:
  - "ChatService rewritten against `agent.iter()` per-node streaming — maps PydanticAI `PartStartEvent` / `PartDeltaEvent` / `FunctionToolCallEvent` / `FunctionToolResultEvent` to the four canonical `StreamEvent` subclasses with the Phase 4.7 wire bytes preserved byte-for-byte."
  - "`search_flights` tool with `ctx: RunContext[ChatDeps]` first parameter — closes the Phase 4.x `_flight_client` monkey-patched attribute back-door (D-06; closes ARCHITECTURE.md 'Monkey-Patched Tool Dependency' Known Tech Debt)."
  - "`InMemoryConversationStore` wired through `api/main.py::lifespan` — Phase 6 swaps for `PostgresConversationStore` via FastAPI DI override (D-08)."
  - "`tests/fixtures/llm.py` rewritten against PydanticAI `FunctionModel(stream_function=...)` — public surface (`Content`/`Thinking`/`ToolCall` chunk types, `MockLLMStream.greeting/single_tool_call/multi_turn`, `make_chat_service_with_mock_llm` signature) preserved per D-17 + D-18."
  - "Wave 3 verify-pass: 290/292 unit+integration tests green; remaining 2 failures are Wave 4 dep-manifest assertions (`langchain*` removal + `pydantic>=2.12` floor) which Plan 05-05 owns."
affects: [05-05-langchain-removal, 06-postgres-conversation-store]

# Tech tracking
tech-stack:
  added:
    - "`pydantic_ai.Agent.iter()` — per-node streaming surface that walks `ModelRequestNode` / `CallToolsNode` so the chat service can emit `StreamEvent`s as PydanticAI surfaces them, instead of accumulating LangChain `AIMessageChunk`s end-to-end."
    - "`pydantic_ai.messages.{PartStartEvent, PartDeltaEvent, TextPart, ThinkingPart, TextPartDelta, ThinkingPartDelta, FunctionToolCallEvent, FunctionToolResultEvent, ToolCallPart, ToolReturnPart, ModelRequest, ModelResponse, UserPromptPart}` — the canonical PydanticAI message + event vocabulary the rewrite consumes."
    - "`pydantic_ai.models.function.{FunctionModel, DeltaToolCall, DeltaThinkingPart}` — the test-fixture substrate replacing LangChain's `MockLLM(BaseChatModel)`."
    - "`Agent.is_model_request_node` / `Agent.is_call_tools_node` static helpers — RESEARCH Pitfall 6 routing pattern."
  patterns:
    - "Lazy import of `search_flights` inside `ChatService.create_session` to break the `app.chat` ↔ `app.tools.flight_search` cycle: PydanticAI's `get_type_hints` on `RunContext[ChatDeps]` requires `ChatDeps` as a runtime symbol in `flight_search.py`, but eager imports through `app.chat/__init__.py` re-trigger the cycle. Lazy-importing the tool inside `create_session` (after `__init__.py` has finished) is the smallest fix."
    - "Per-tool-call timing via `tool_call_start: dict[tool_call_id, time.monotonic()]`: stamped on `FunctionToolCallEvent`, popped on `FunctionToolResultEvent`. Keeps timing per-tool-call rather than relying on a single wall-clock variable that races between concurrent calls."
    - "`StreamsArg = list[list[Chunk]] | Callable[[], None]` widening on `make_chat_service_with_mock_llm`: extends the fixture surface with an error-injection path (zero-arg callable that raises) without breaking D-18's positional-call shape. The `tests/unit/chat/test_stream_error_event.py` Wave 0 RED test pinned this contract."

key-files:
  created:
    - "`backend/tests/integration/test_chat_stream.py` — three locked scenarios drive `make_chat_service_with_mock_llm`."
    - "`backend/tests/integration/test_chat_factory.py` — pins the factory's signature (D-18)."
  modified:
    - "`backend/app/tools/flight_search.py` — drops `@tool` decorator + `_flight_client` back-door; gains `ctx: RunContext[ChatDeps]` first parameter."
    - "`backend/app/chat/service.py` — full rewrite of `__init__` (gains `conversation_store`), `create_session` (builds `Agent`), `chat_stream` (per-node `agent.iter()` loop), `cleanup_expired_sessions` (now async), `list_sessions_for_user` / `get_history_for_user` (read PydanticAI `ModelMessage` shape via the store). Adds `delete_session` for the route layer; removes `get_session_history` (LangChain-only return type)."
    - "`backend/app/api/main.py::lifespan` — constructs `InMemoryConversationStore`; deletes `search_flights._flight_client = flight_client` and the unused `from app.tools.flight_search import search_flights` import; awaits `cleanup_expired_sessions` on shutdown."
    - "`backend/app/api/routes/routes.py::DELETE /api/chat/session/{id}` — replaces inline `_histories.pop` / `_bound_providers.pop` with `await chat_service.delete_session(session_id)`."
    - "`backend/tests/fixtures/llm.py` — drops `MockLLM(BaseChatModel)` + `_MockBoundProvider`; new `_MockLLMProvider(LLMProvider)` builds an `Agent` from `FunctionModel(stream_function=...)`. Public surface preserved per D-17 + D-18."
    - "`backend/tests/unit/test_chat_stream.py` — replaces LangChain `patch.object(type(search_flights), 'ainvoke', ...)` style with `streams: Callable[[], None]` error injection."
    - "`backend/tests/unit/test_chat_service.py` — drops module-level `pytest.skip`; rewrites onto `_agents` lifecycle + `ConversationStore` persistence."
    - "`backend/tests/integration/test_chat_service_flow.py` — history assertions migrate to PydanticAI `ModelRequest`/`ModelResponse` shape (`UserPromptPart`/`TextPart`/`ToolCallPart`/`ToolReturnPart`)."
    - "`backend/tests/integration/test_session.py` — `_histories` references replaced with `_agents` + the InMemory `_store` dict."
    - "`backend/tests/integration/test_session_history_route.py` — seed `ModelRequest`/`ModelResponse` parts via the InMemoryConversationStore instead of LangChain `HumanMessage`/`AIMessage`."
    - "`backend/tests/integration/test_session_partitioning.py` — `_histories.clear()` + `_bound_providers.clear()` retired in favour of `_agents.clear()`; the metadata-only seeding shape replaces the LangChain history seeding."
    - "`backend/tests/unit/api/test_chat_sessions_route.py` — `_reset_chat_service` helper replaces inline `_histories.clear()`/`_bound_providers.clear()`; `first_message_preview` test seeds via the ConversationStore."
    - "`backend/tests/unit/test_tool_json_normalization.py::test_search_flights_returns_json_envelope_string` — drives `search_flights(ctx, ...)` with a real `RunContext[ChatDeps]` carrying a deterministic `MockFlightAPIClient`."

key-decisions:
  - "Lazy import of `search_flights` inside `ChatService.create_session` (vs. eager top-of-module): PydanticAI's `get_type_hints` evaluates the deferred `ctx: RunContext[ChatDeps]` annotation in `flight_search.py`'s globals at `Agent` construction time, so `ChatDeps` must be a real runtime symbol there. The eager-import path runs through `app.chat/__init__.py`, which loads `ChatService` and triggers the cycle. The smallest fix is to make `service.py` import `search_flights` LAZILY inside `create_session` — `__init__.py` has finished by then, so `app.chat.deps` is fully resolvable from the tool module."
  - "Per-tool-call timing via `tool_call_start: dict[str, float]` (vs. a single wall-clock variable): RESEARCH suggested `elapsed_ms=0` would be acceptable but the implementer chose to thread `time.monotonic()` from `FunctionToolCallEvent` to `FunctionToolResultEvent` via the `tool_call_id` so the SSE wire keeps the Phase 4.7 elapsed-ms field populated meaningfully. Cost: one dict lookup per tool event; gain: identical UI rendering for `ToolExecutionCard`."
  - "`StreamsArg = list[list[Chunk]] | Callable[[], None]` widening on `make_chat_service_with_mock_llm` (vs. a separate `make_chat_service_with_failing_llm` factory): the Wave 0 `test_stream_error_event.py` test passes a zero-arg callable through `make_chat_service_with_mock_llm`, pinning the contract. A separate factory would have required test-side type annotations + duplication of the construction logic."
  - "Use `Agent.is_model_request_node` / `Agent.is_call_tools_node` static helpers (vs. importing `_agent_graph.{ModelRequestNode, CallToolsNode}` from PydanticAI's underscore-prefixed implementation surface): RESEARCH Pitfall 6 explicitly recommends the public helpers — they preserve generic parameters that direct `isinstance` checks lose, and they're the stable surface across PydanticAI patch versions."
  - "`StreamEvent` ABC + concrete classes serialise byte-identical to Phase 4.7 — verified by the wire-byte golden file in `tests/unit/chat/test_stream_event_wire_compat.py` (5/5 PASS). The frontend's SSE parser is unchanged."

patterns-established:
  - "Pattern: PydanticAI per-node streaming loop. `async with agent.iter(message, message_history=history, deps=deps) as agent_run` + `async for node in agent_run` + `if Agent.is_model_request_node(node): async with node.stream(agent_run.ctx) as model_stream: async for event in model_stream: ...`. The four event mappings live in two helpers (`_map_model_request_event` for text/thinking, `_handle_tool_event` for tool call/result) so the main loop body stays at one screen."
  - "Pattern: Lazy import to break PydanticAI's `RunContext[T]` annotation cycles. When a tool annotates `ctx: RunContext[T]` and `T` lives in the same package as the consumer (e.g. `ChatService`), the package's `__init__.py` is the cycle vertex. Solution: import the tool LAZILY at the consumer's first-use site, not at the consumer's module top. Generalises to Phase 6's PostgresConversationStore wiring."

requirements-completed: [REQ-pydantic-ai-migration]  # advances; full satisfaction lands when Wave 4 (Plan 05-05) removes `langchain*` from the manifest. Plan-level success criteria (SC-1 / SC-2 / SC-5) are fully satisfied — see <plan_level_success_criteria> below.

# Metrics
duration: ~31min
completed: 2026-06-03
---

# Phase 5 Plan 04: Wave 3 — ChatService rewrite (PydanticAI agent.iter() goes live) Summary

**`ChatService.chat_stream` now drives a per-session `pydantic_ai.Agent` via `agent.iter()`, mapping PydanticAI's `PartStartEvent`/`PartDeltaEvent`/`FunctionToolCallEvent`/`FunctionToolResultEvent` to the four `StreamEvent` subclasses with byte-identical SSE wire bytes; `search_flights` reads its `FlightAPIClient` from `RunContext[ChatDeps]` (back-door closed); `InMemoryConversationStore` is wired through `api/main.py`'s lifespan; the `MockLLMStream` fixture rebuilt on PydanticAI `FunctionModel(stream_function=...)` with the D-17/D-18 public surface preserved.**

## Performance

- **Duration:** ~31 min
- **Started:** 2026-06-03 07:39:40Z
- **Completed:** 2026-06-03 ~08:10Z
- **Tasks:** 4 of 5 (Task 5 is a manual UAT checkpoint — see "Manual UAT Status" below)
- **Files modified:** 13 (4 application + 9 tests + 2 new test files)

## Accomplishments

- **Task 1 — `search_flights` rewrite (commit `d9c9b89`).** Drops the `@tool` decorator + `langchain_core.tools.tool` import. Adds `ctx: RunContext[ChatDeps]` as the first positional parameter; the body's `client = ctx.deps.flight_client` line replaces the Phase 4.x `getattr(search_flights, "_flight_client", None)` back-door, and the `if client is None: ...` defensive branch is deleted (non-None by type). The Wave 0 anti-pattern lock (`tests/unit/tools/test_flight_search_no_backdoor.py`) turns GREEN; the JSON-normalization test (`test_tool_json_normalization::test_search_flights_returns_json_envelope_string`) is rewired to drive the function with a real `pydantic_ai.RunContext` carrying a deterministic `MockFlightAPIClient`. Closes ARCHITECTURE.md "Monkey-Patched Tool Dependency" Known Tech Debt entry.

- **Task 2 — `tests/fixtures/llm.py` rewrite (commit `45b53aa`).** Drops `MockLLM(BaseChatModel)` + `_MockBoundProvider`; the new `_MockLLMProvider(LLMProvider)` subclasses the Phase 5 ABC explicitly (D-03) and its `build_agent` returns `Agent(FunctionModel(stream_function=_make_stream_function(streams)), tools=list(tools), deps_type=deps_type)`. The closure consumes one inner `list[Chunk]` per stream invocation (RESEARCH Pitfall 7 — `single_tool_call` returns TWO inner lists). Public surface (`Content`/`Thinking`/`ToolCall` `@dataclass(frozen=True, slots=True)` + the three `MockLLMStream` classmethods + `make_chat_service_with_mock_llm(streams)` signature) preserved per D-17 + D-18. The fixture compiles cleanly; full integration sees in Task 4.

- **Task 3 — `ChatService` rewrite + lifespan wiring (commit `ea8cde2`).** This is the centerpiece of the migration. `ChatService.__init__` gains `conversation_store: ConversationStore` (D-08); `_histories: dict[str, InMemoryChatMessageHistory]` retires in favour of the store seam; `_bound_providers: dict[str, Any]` retires in favour of `_agents: dict[str, Agent[ChatDeps, str]]` (D-10). The Phase 4.x `search_flights._flight_client = flight_client` monkey-patch is deleted from `__init__`. `create_session` builds `Agent` via `provider.build_agent(tools=[search_flights], deps_type=ChatDeps)` and stashes it in `_agents`. `chat_stream` walks `async with agent.iter(...) as agent_run` + `async for node in agent_run`, using `Agent.is_model_request_node` / `Agent.is_call_tools_node` static helpers (RESEARCH Pitfall 6) to route per-node streaming. Two private helpers (`_map_model_request_event`, `_handle_tool_event`) map PydanticAI's events into the four StreamEvent subclasses; `_metadata[session_id]["last_tool_invocation"]` write inside the tool-call branch (D-09 — Phase 4.7 retry endpoint depends on it) is preserved. `cleanup_expired_sessions` flips to `async def` (Assumption A1). Exception handler emits `ErrorEvent(error_code=tool_error|stream_error, raw_detail=_scrub(str(exc)))` per the Phase 4.7 contract. `api/main.py::lifespan` constructs `InMemoryConversationStore()` and threads it into `ChatService`; the back-door injection line is deleted; the shutdown call awaits the now-async cleanup. `routes.py::DELETE` switches to `await chat_service.delete_session(session_id)`. The Wave 0 chat-package tests (22/22) pass; SSE wire-byte golden file passes 5/5.

- **Task 4 — Test retarget (commit `17e055c`).** Two new integration files (`test_chat_stream.py` + `test_chat_factory.py`) and three rewritten test files (`test_chat_service_flow.py` + `test_chat_stream.py` + `test_chat_service.py`) cover the new API. Plus four blocking-rule sweeps for tests broken by Task 3's `_histories`/`_bound_providers` retirement (`test_session.py`, `test_session_history_route.py`, `test_session_partitioning.py`, `test_chat_sessions_route.py`). Test sweep result: 290 PASS / 2 FAIL / 5 SKIP, where the 2 failures are Wave 4 dep-manifest assertions in `test_dependencies.py` (Plan 05-05 scope).

- **`mypy --strict`** on `app/chat/`, `app/api/main.py`, and `app/tools/flight_search.py` returns 3 pre-existing errors (none introduced by this plan): `models.py:114` is the Wave 1 `StreamEvent.__get_pydantic_core_schema__` valid-type warning (intentional — see `app/chat/models.py` docstring), and `routes.py:103` + `routes.py:208` are pre-existing `StreamEvent.model_dump_json()` patterns from Phase 4.7 (StreamEvent is the marker ABC; `model_dump_json` lives on the concrete subclasses returned by `chat_stream`). All other modules under check are strict-clean.

- **`grep -rEn '^(from |import )langchain' backend/app`** returns zero matches in `app/`. The only LangChain references that remain in the repo are in `pyproject.toml` (Wave 4 / Plan 05-05 scope) and in `tests/conftest.py` (a `BaseChatModel`-based legacy fixture also scheduled for Wave 4 cleanup).

## Stream Event Mapping Table

| PydanticAI event | StreamEvent subclass | Notes |
|------------------|----------------------|-------|
| `PartStartEvent` + `ThinkingPart(content=c)` (truthy) | `ThinkingEvent(chunk=c, session_id=...)` | Empty content skipped — no no-op chunks. |
| `PartDeltaEvent` + `ThinkingPartDelta(content_delta=d)` (truthy) | `ThinkingEvent(chunk=d, session_id=...)` | qwen3 `<think>` deltas surface here. |
| `PartStartEvent` + `TextPart(content=c)` (truthy) | `ContentEvent(chunk=c, session_id=...)` | Initial assistant chunk. |
| `PartDeltaEvent` + `TextPartDelta(content_delta=d)` (truthy) | `ContentEvent(chunk=d, session_id=...)` | Subsequent assistant deltas. |
| `FunctionToolCallEvent` (carries `ToolCallPart`) | `ToolCallEvent(tool_name, tool_args, session_id)` | `tool_args` normalised dict-or-string per Pitfall 3. ALSO writes `_metadata[..]["last_tool_invocation"]` (D-09). Stamps `tool_call_start[tool_call_id] = time.monotonic()`. |
| `FunctionToolResultEvent` + `ToolReturnPart` | `ToolResultEvent(tool_name, tool_result, elapsed_ms, session_id)` | `elapsed_ms = (time.monotonic() - tool_call_start.pop(tool_call_id)) * 1000`. |
| Any exception in `agent.iter()` body | `ErrorEvent(error_code, message, retryable, raw_detail=_scrub(str(exc)), session_id)` | `APIError` → `tool_error` + `retryable=exc.retryable`; any other `Exception` → `stream_error` + `retryable=False`. `_scrub` from `app.llm.log_scrubbing` (Phase 4.7 contract). |

## Task Commits

Each task committed atomically:

1. **Task 1: search_flights rewrite** — `d9c9b89` (refactor)
2. **Task 2: tests/fixtures/llm.py rewrite** — `45b53aa` (refactor)
3. **Task 3: ChatService rewrite + lifespan wiring** — `ea8cde2` (refactor)
4. **Task 4: integration + unit chat tests retarget** — `17e055c` (test)
5. **Task 5: Manual UAT** — DEFERRED (see "Manual UAT Status" below)

## Manual UAT Status (Task 5)

Task 5 is `type="checkpoint:human-verify"` (gate=blocking). It requires running the full backend + frontend against a real Ollama daemon with `qwen3:4b` and exercising the chat path end-to-end. **The executor is running inside an isolated git worktree without access to the user's local Ollama daemon, so this checkpoint cannot be auto-completed.**

**UAT steps to run after merge** (per the plan's `<how-to-verify>`):

1. Ensure Ollama is running locally and `qwen3:4b` is pulled (`ollama list | grep qwen3`).
2. From the repo root: `just backend` (terminal A) and `just frontend` (terminal B).
3. Open `http://localhost:5173`, log in with the `AUTH_USERS`-seeded credentials.
4. Pick provider=Ollama, model=`qwen3:4b`. Confirm the session is created without error.
5. Send the prompt: "find flights JFK→LAX 2026-07-15".
6. Confirm: a `ThinkingCard` renders (qwen3 produces `<think>` tags); a `ToolExecutionCard` renders showing the `search_flights` tool call AND its result (mock-flight rows); the final assistant message renders with markdown intact.
7. Send a follow-up: "what's the cheapest one?". Confirm conversation history works (the model references the prior search).
8. (Optional) Stop Ollama, send a new message — confirm an `ErrorEvent` toast appears in the UI rather than a silent hang.

If any step fails, the merge to `master` should be reverted and the failure investigated before Wave 4 begins. The orchestrator (or the user via the resume signal) gates Wave 4 (`Plan 05-05 — LangChain removal`) on this UAT passing.

## Files Created/Modified

### Created
- `backend/tests/integration/test_chat_stream.py` — three locked scenarios drive `make_chat_service_with_mock_llm`.
- `backend/tests/integration/test_chat_factory.py` — pins the factory's signature (D-18).

### Modified

| File | Diff summary |
|------|--------------|
| `backend/app/tools/flight_search.py` | Drop `@tool` + `langchain_core.tools.tool`; add `ctx: RunContext[ChatDeps]` first param; replace `getattr(search_flights, "_flight_client", None)` with `ctx.deps.flight_client`; remove `if client is None:` defensive branch. |
| `backend/app/chat/service.py` | Full rewrite — `_histories` → `_conversation_store`; `_bound_providers` → `_agents`; `chat_stream` rewritten on `agent.iter()`; `cleanup_expired_sessions` flips to async; `delete_session` added; `get_session_history` removed; LangChain imports gone. |
| `backend/app/api/main.py` | Construct `InMemoryConversationStore`; thread into `ChatService`; delete back-door injection line; await async cleanup. |
| `backend/app/api/routes/routes.py` | DELETE `/api/chat/session/{id}` switches to `await chat_service.delete_session(session_id)`. |
| `backend/tests/fixtures/llm.py` | Drop `MockLLM(BaseChatModel)` + `_MockBoundProvider`; new `_MockLLMProvider(LLMProvider)` builds `Agent` from `FunctionModel(stream_function=...)`; `StreamsArg` widening for error injection. |
| `backend/tests/integration/test_chat_service_flow.py` | History assertions migrate to PydanticAI `ModelRequest`/`ModelResponse` shape. |
| `backend/tests/integration/test_session.py` | `_histories` → `_agents` + `_conversation_store._store`. |
| `backend/tests/integration/test_session_history_route.py` | Seed `ModelRequest`/`UserPromptPart` + `ModelResponse`/`TextPart` parts via the InMemoryConversationStore. |
| `backend/tests/integration/test_session_partitioning.py` | `_histories.clear()` + `_bound_providers.clear()` retired in favour of `_agents.clear()`. |
| `backend/tests/unit/api/test_chat_sessions_route.py` | `_reset_chat_service` helper; seed `ModelRequest`/`UserPromptPart` for the preview test. |
| `backend/tests/unit/test_chat_stream.py` | Replace `patch.object(type(search_flights), "ainvoke", ...)` with `streams: Callable[[], None]` error injection; history reads via `_conversation_store.load`. |
| `backend/tests/unit/test_chat_service.py` | Drop module-level `pytest.skip`; rewrite onto `_agents` + `ConversationStore` semantics. |
| `backend/tests/unit/test_tool_json_normalization.py::test_search_flights_returns_json_envelope_string` | Drive `search_flights(ctx, ...)` with a real `RunContext[ChatDeps]`. |

## Decisions Made

- **Lazy import of `search_flights` inside `ChatService.create_session`** (rather than the more common module-top import). Drove by PydanticAI's `get_type_hints` evaluating `RunContext[ChatDeps]` at `Agent` construction time, which requires `ChatDeps` as a runtime symbol in `flight_search.py`'s globals. The eager-import path runs through `app.chat/__init__.py` → loads `ChatService` → triggers the cycle. Lazy-importing inside the consumer method (after `__init__.py` has completed) is the smallest fix; alternative was breaking up `app.chat/__init__.py` to not import `ChatService` eagerly, which would cascade through every caller.
- **Per-tool-call timing via `tool_call_start: dict[str, float]`** (vs. `elapsed_ms=0` per RESEARCH guidance). The implementer chose to thread `time.monotonic()` from `FunctionToolCallEvent` to `FunctionToolResultEvent` via `tool_call_id` so the SSE wire keeps Phase 4.7's elapsed-ms field meaningful. Cost: one dict lookup per tool event; gain: the frontend's `ToolExecutionCard` keeps rendering elapsed time identically to Phase 4.7.
- **`StreamsArg = list[list[Chunk]] | Callable[[], None]` widening** on `make_chat_service_with_mock_llm` (vs. a separate factory). The Wave 0 `test_stream_error_event.py` test passes a zero-arg callable through the existing factory; widening preserves D-18's positional shape and avoids duplicating the construction logic in a parallel factory.
- **`Agent.is_model_request_node` / `Agent.is_call_tools_node` static helpers** (vs. importing `_agent_graph.{ModelRequestNode, CallToolsNode}` from PydanticAI's underscore-prefixed implementation surface). RESEARCH Pitfall 6 explicitly recommends the public helpers; they preserve generic parameters that direct `isinstance` checks lose, and they're the stable surface across PydanticAI patch versions.
- **`event.part` (not `event.result`)** when reading `FunctionToolResultEvent`. PydanticAI 1.x emits a `DeprecationWarning` on `.result`; the part-attribute spelling is the post-1.x canonical. Cleaner Phase 8 structlog migration.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] `app.chat/__init__.py` ↔ `app.tools.flight_search` circular import after the `from app.chat.deps import ChatDeps` addition**
- **Found during:** Task 1 (verifying the imports compile).
- **Issue:** Adding `from app.chat.deps import ChatDeps` to `app/tools/flight_search.py` triggers `app/chat/__init__.py`, which loads `ChatService` (currently imports `search_flights` at the module top), which re-enters `app/tools/flight_search.py` while `ChatDeps` is still being resolved → `ImportError`. PydanticAI requires `ChatDeps` to be a real runtime symbol in `flight_search.py` (its `get_type_hints` evaluates the `ctx: RunContext[ChatDeps]` annotation at `Agent` construction time, against the function's module globals).
- **Fix:** Move the `from app.tools.flight_search import search_flights` import inside `ChatService.create_session` (lazy at first-use, after `__init__.py` has finished). The annotation in `flight_search.py` stays a runtime import. Documented in both files' docstrings + a `noqa: PLC0415` comment at the lazy-import site.
- **Files modified:** `backend/app/chat/service.py`, `backend/app/tools/flight_search.py`
- **Verification:** `python -c "import app.tools.flight_search"`, `python -c "from app.api.main import app"` both succeed; `tests/unit/tools/test_flight_search_no_backdoor.py` 2/2 PASS; full Wave 0 chat suite 22/22 PASS.
- **Committed in:** `d9c9b89` (Task 1) + `ea8cde2` (Task 3 — when the lazy import was finalised inside the rewritten `create_session`).

**2. [Rule 3 - Blocking] `tests/unit/test_tool_json_normalization::test_search_flights_returns_json_envelope_string` references the retired `search_flights._flight_client` back-door**
- **Found during:** Task 1 verify.
- **Issue:** The test was the canonical Phase 4.x demo of the back-door pattern (set `search_flights._flight_client = MockFlightAPIClient(seed=42)`, call `search_flights.ainvoke(...)`). Both surfaces retire in this plan.
- **Fix:** Rewrite the test to construct a real `pydantic_ai.RunContext` carrying `ChatDeps(flight_client=MockFlightAPIClient(seed=42), session_id="test-session", user_id="test-user")` and call `await search_flights(ctx, origin="LAX", ...)` directly. Same JSON-envelope assertion; new dependency-injection shape.
- **Files modified:** `backend/tests/unit/test_tool_json_normalization.py`
- **Verification:** `tests/unit/test_tool_json_normalization.py` 12/12 PASS.
- **Committed in:** `d9c9b89` (Task 1).

**3. [Rule 3 - Blocking] Four test files reference the retired `_histories` / `_bound_providers` / LangChain `InMemoryChatMessageHistory` after the Task 3 rewrite**
- **Found during:** Task 4 (post-rewrite test sweep).
- **Issue:** The plan's `<files_modified>` for Task 4 lists 5 files; an additional 4 files (`test_session.py`, `test_session_history_route.py`, `test_session_partitioning.py`, `test_chat_sessions_route.py`) seed history through the LangChain-shape collections that retire in Task 3. Without rewriting them, the broader unit + integration test suite blocks (which would forbid the next plan from establishing a clean baseline).
- **Fix:** Rewrite each of the 4 files to seed via the InMemoryConversationStore's `_store` dict (with PydanticAI `ModelRequest`/`ModelResponse` parts) and to assert on `_agents` + `_metadata` rather than `_histories` + `_bound_providers`. Same intent, new shape.
- **Files modified:** `backend/tests/integration/test_session.py`, `backend/tests/integration/test_session_history_route.py`, `backend/tests/integration/test_session_partitioning.py`, `backend/tests/unit/api/test_chat_sessions_route.py`
- **Verification:** All 4 files pass under the new shape; broader sweep is 290 PASS / 2 FAIL / 5 SKIP (where the 2 failures are Wave 4 dep-manifest assertions, NOT regressions from this fix).
- **Committed in:** `17e055c` (Task 4).

**4. [Rule 1 - Bug] `FunctionToolResultEvent.result` emits `DeprecationWarning` in PydanticAI 1.x**
- **Found during:** Task 3 verify.
- **Issue:** RESEARCH guidance referenced `event.result` in the example streaming loop, but that attribute is a deprecated alias as of PydanticAI 1.x. The first run of `tests/unit/chat/` showed two `DeprecationWarning`s on `result` — would surface in Phase 8 structlog as noise.
- **Fix:** Switch to `event.part`. Behaviour-identical; cleaner test logs.
- **Files modified:** `backend/app/chat/service.py`
- **Verification:** `tests/unit/chat/test_stream_event_extraction.py` 4/4 PASS with no DeprecationWarnings.
- **Committed in:** `ea8cde2` (Task 3).

---

**Total deviations:** 4 auto-fixed (3 Rule 3 blocking + 1 Rule 1 bug).
**Impact on plan:** All four were necessary to satisfy this plan's verify scope. The lazy-import deviation (#1) is a structural improvement worth landing in the SUMMARY's "Decisions Made" because the pattern recurs (Phase 6 `PostgresConversationStore` will face the same cycle when the conversation-store module ends up imported by the same chat package). The four blocking-rule sweeps (#3) are scope-aligned with Task 4 even though the file list slightly extends the plan's `<files_modified>`.

## Issues Encountered

- **PydanticAI 1.x's `_agent_graph.{ModelRequestNode, CallToolsNode}` is an underscore-prefixed implementation surface.** RESEARCH Pitfall 6 already flagged this; the implementer used the public `Agent.is_model_request_node` / `Agent.is_call_tools_node` static helpers instead, which preserve generic parameters and are stable across patch versions.

- **PydanticAI 1.x reorders the `__init__` signature on `FunctionToolResultEvent` (the field is `part`, not `result`).** Documented in the deviation #4 above; the rewrite reads `event.part`.

- **`from __future__ import annotations` does NOT defer the annotation evaluation that PydanticAI's `Agent` constructor performs.** PydanticAI uses `typing.get_type_hints` to resolve `ctx: RunContext[ChatDeps]` against the function's module globals — which forces `ChatDeps` to be a real runtime symbol. The lazy-import workaround (deviation #1) is the resolution.

## User Setup Required

None — no env vars, dashboard configs, or external services touched. All changes are internal refactors of the chat-service substrate.

The Task 5 manual UAT step requires a running Ollama daemon with `qwen3:4b` pulled, but that's a developer-environment prerequisite (already satisfied by anyone running Phase 4.x locally) — not a "user setup" concern.

## Confirmation: No `langchain*` imports in `app/`

```bash
$ grep -rEn '^(from |import )langchain' backend/app
(no output)
```

The only `langchain*` references that remain in the repo are:

- `backend/pyproject.toml` — Wave 4 (Plan 05-05) scope.
- `backend/tests/conftest.py` — uses `from langchain_core.language_models.chat_models import BaseChatModel` for a legacy fixture; Wave 4 deletes the fixture along with the dep removal.

## Confirmation: SSE wire-byte golden file (Phase 4.7 byte-equivalence)

```
$ uv run pytest tests/unit/chat/test_stream_event_wire_compat.py -v
tests/unit/chat/test_stream_event_wire_compat.py::test_content_event_wire_unchanged PASSED
tests/unit/chat/test_stream_event_wire_compat.py::test_thinking_event_wire_unchanged PASSED
tests/unit/chat/test_stream_event_wire_compat.py::test_tool_call_event_wire_unchanged PASSED
tests/unit/chat/test_stream_event_wire_compat.py::test_tool_result_event_wire_unchanged PASSED
tests/unit/chat/test_stream_event_wire_compat.py::test_error_event_wire_unchanged PASSED
============================== 5 passed in 0.02s ===============================
```

The frontend SSE parser is unaffected by the rewrite — wire bytes are byte-identical to Phase 4.7.

## Self-Check: PASSED

Files claimed to exist after Plan 05-04:

- `backend/app/tools/flight_search.py` (rewritten with `RunContext[ChatDeps]`) — FOUND
- `backend/app/chat/service.py` (rewritten on `agent.iter()`) — FOUND
- `backend/app/api/main.py` (lifespan wires `InMemoryConversationStore`) — FOUND
- `backend/app/api/routes/routes.py` (DELETE switches to `delete_session`) — FOUND
- `backend/tests/fixtures/llm.py` (rewritten on `FunctionModel`) — FOUND
- `backend/tests/integration/test_chat_stream.py` (NEW) — FOUND
- `backend/tests/integration/test_chat_factory.py` (NEW) — FOUND
- `backend/tests/integration/test_chat_service_flow.py` (rewritten) — FOUND
- `backend/tests/unit/test_chat_stream.py` (rewritten) — FOUND
- `backend/tests/unit/test_chat_service.py` (rewritten) — FOUND
- `.planning/phases/05-pydanticai-migration/05-04-SUMMARY.md` (this file) — FOUND

Commit hashes claimed:

- `d9c9b89` (Task 1 — `search_flights` rewrite) — FOUND in git log
- `45b53aa` (Task 2 — fixture rewrite) — FOUND in git log
- `ea8cde2` (Task 3 — ChatService rewrite + lifespan wiring) — FOUND in git log
- `17e055c` (Task 4 — test retarget + four blocking-rule sweeps) — FOUND in git log

Verification summary:

- `pytest tests/unit/chat/` — 22/22 PASS (Wave 0 chat suite + wire-byte golden file).
- `pytest tests/unit/ tests/integration/` — 290 PASS, 2 FAIL (Wave 4 dep-manifest in `test_dependencies.py`), 5 SKIP. The 2 failures are Plan 05-05 scope.
- `mypy --strict app/chat/ app/api/main.py app/tools/flight_search.py` — 3 pre-existing errors, none introduced by this plan (Wave 1 ABC schema warning + 2 pre-existing `model_dump_json` access patterns in routes.py).
- `grep -rEn '^(from |import )langchain' backend/app` — zero matches.

## Plan-level Success Criteria

ROADMAP.md Phase 5 advancement (per the plan's `<success_criteria>`):

- **SC-1** — ChatService orchestrates a PydanticAI Agent per session; tool registration via PydanticAI; `_flight_client` back-door replaced. ✅ DONE.
- **SC-2** — StreamEvent ABC over SSE preserved frontend-side; backend extraction rewritten. ✅ DONE.
- **SC-5** — `MockLLMStream` updated for PydanticAI surface; default `pytest` fast and offline. ✅ DONE.

Plan-level criteria from `<success_criteria>`:

- [x] `search_flights` first parameter is `ctx: RunContext[ChatDeps]`; the `_flight_client` attribute is gone everywhere.
- [x] `ChatService.chat_stream` uses `agent.iter()`; emits the four StreamEvent subclasses + ErrorEvent on exception.
- [x] `api/main.py::lifespan` constructs `InMemoryConversationStore` and passes it to `ChatService`; the back-door injection line is deleted.
- [x] The fixture rewrite preserves `make_chat_service_with_mock_llm` signature (D-18).
- [ ] Manual UAT against qwen3:4b succeeds end-to-end. **PENDING — requires human verification (see "Manual UAT Status" above). Wave 4 (Plan 05-05) gates on this passing.**

## Next Phase Readiness

- **Wave 4 / Plan 05-05 (LangChain dependency removal)** can run as soon as the manual UAT (Task 5) passes. The plan's job is to (a) `uv remove langchain langchain-core langchain-ollama langchain-openai langchain-anthropic langgraph`, (b) bump `pydantic>=2.12` floor, (c) regenerate `uv.lock`, (d) clean up the lone LangChain-shaped fixture in `tests/conftest.py`. The `test_dependencies.py` Wave 0 RED tests turn green when the dep removal lands.
- **Phase 6 (PostgresConversationStore swap)** — the `ConversationStore` ABC is now consumed end-to-end through `ChatService`; the swap is a single FastAPI DI override in `api/main.py::lifespan`. The lazy-import pattern documented above generalises if the Postgres impl module ends up imported by `app.chat`'s `__init__.py`.
- **Phase 8 (structlog migration)** — the rewrite emits no `print` calls; `_scrub` is the only side-channel stripped from `ErrorEvent.raw_detail`. structlog's processor pipeline can replace `_scrub` cleanly.

---

*Phase: 05-pydanticai-migration*
*Plan: 04 (Wave 3 — ChatService rewrite + agent.iter() goes live)*
*Completed: 2026-06-03*
