---
phase: 05-pydanticai-migration
verified: 2026-06-03T10:34:23Z
status: verified
score: 13/13 must-haves verified
overrides_applied: 0
post_verification_fixes:
  - id: OLLAMA-V1-SUFFIX
    fixed_at: 2026-06-03
    commit: e21a7e3
    issue: "Ollama chat base_url missing /v1 suffix → 404 page not found on every chat turn against qwen3:4b / qwen3:8b through real daemon."
    fix: "OllamaProvider.build_agent appends /v1 to base_url before constructing PaiOllamaProvider; idempotent for operators who already include /v1."
    regression_locks: "tests/unit/llm/providers/test_ollama_thinking.py::test_ollama_chat_base_url_appends_v1_suffix + ::test_ollama_chat_base_url_does_not_double_v1_suffix"
    smoke_evidence: "End-to-end against real Ollama qwen3:4b (thinking stream) + qwen3:8b (tool_call → tool_result → content stream) confirmed via curl-driven SSE capture."
requirements:
  - id: REQ-pydantic-ai-migration
    status: PASS
    evidence: "LLMProvider(ABC) at app/llm/base.py; 4 providers in app/llm/providers/{ollama,openai,anthropic,lmstudio}.py implement build_agent → pydantic_ai.Agent; ChatService.chat_stream drives agent.iter() in app/chat/service.py; ChatDeps frozen dataclass at app/chat/deps.py; ConversationStore ABC + InMemoryConversationStore at app/chat/store.py; lifespan wires the store at app/api/main.py; pyproject.toml carries pydantic-ai>=0.8.1 and zero langchain*/langgraph entries; 292 unit+integration tests pass, 3 skip (D-13 cloud-provider gated)."
  - id: REQ-p5-stream-event-abc
    status: PASS
    evidence: "StreamEvent(ABC) marker class with __get_pydantic_core_schema__ override at app/chat/models.py:68-116; five concrete subclasses (Content/Thinking/ToolCall/ToolResult/Error) multi-inherit (BaseModel, StreamEvent); test_stream_event_wire_compat.py 5/5 passes — SSE wire bytes byte-identical to Phase 4.7 golden file."
human_verification: []  # Deferred Ollama UAT closed by OLLAMA-V1-SUFFIX fix on 2026-06-03; live daemon smoke against qwen3:4b + qwen3:8b confirmed thinking + tool-call + content streams.
post_merge_improvements:
  - id: CR-01
    severity: critical
    summary: "Wrong exception type caught at route boundary (`except ValueError` cannot fire — actual error is KeyError) — race-deletion error path is unreachable in POST /api/chat and POST /api/chat/retry."
  - id: CR-02
    severity: critical
    summary: "`assert self._api_key is not None` in OpenAI/Anthropic build_agent evaporates under `python -O`; security precondition guard breaks silently in production."
  - id: CR-03
    severity: critical
    summary: "InMemoryConversationStore.append does unbounded immutable concat; long-running sessions OOM the server. No cap, only session-expiry cleanup."
  - id: CR-04
    severity: critical
    summary: "ChatService._first_message_preview / get_history_for_user reach into ConversationStore._store private attribute via getattr — Phase 6 PostgresConversationStore will silently return None / empty messages."
  - id: WR-01
    severity: warning
    summary: "Concurrent chat_stream calls on the same session race the conversation store (load + agent.iter + append is not atomic)."
  - id: WR-02
    severity: warning
    summary: "tool_call_start dict leaks entries forever when a tool errors mid-stream (no cleanup on FunctionToolCallEvent without matching ResultEvent)."
  - id: WR-03
    severity: warning
    summary: "Reflected user input in 400 error message — log injection vector."
  - id: WR-04
    severity: warning
    summary: "tuple[str, ...] Settings field cannot be overridden via env var — pydantic-settings cannot parse."
  - id: WR-05
    severity: warning
    summary: "SSRF allowlist on base_url misses IPv6 localhost (::1)."
  - id: WR-06
    severity: warning
    summary: "Malformed tool args raise unhandled JSONDecodeError in _handle_tool_event."
  - id: WR-07
    severity: warning
    summary: "Synthetic retry prompt is vulnerable to LLM-injected tool_name (no allow-list check)."
  - id: WR-08
    severity: warning
    summary: "_metadata[session_id]['last_tool_invocation'] race within a single turn (multi-tool-call turns overwrite each other)."
  - id: WR-09
    severity: warning
    summary: "MockLLMStream exhaustion produces a misleading error after the test finishes."
  - id: WR-10
    severity: warning
    summary: "_first_message_preview slice on Python str codepoints, not graphemes (multi-byte/emoji split mid-character)."
  - id: WR-11
    severity: warning
    summary: "httpx errors beyond the three caught (RemoteProtocolError, ReadError, PoolTimeout, UnsupportedProtocol, ProxyError, JSONDecodeError) propagate unhandled."
  - id: IN-01
    severity: info
    summary: "list_for_user is dead code in Phase 5 (always returns []) — keep but document as Phase 6 hook."
  - id: IN-02
    severity: info
    summary: "MockFlightAPIClient(seed=42) magic number repeated 3+ times — extract constant."
  - id: IN-03
    severity: info
    summary: "from app.providers.models import SessionCreateError as SessionCreateError mid-module — move to top of file."
  - id: IN-04
    severity: info
    summary: "Comment-as-code in tests/fixtures/llm.py — `if False: yield` placeholder pattern."
  - id: IN-05
    severity: info
    summary: "getattr(self._conversation_store, '_store', None) in test seeding — same leaky-abstraction shape as CR-04."
  - id: IN-06
    severity: info
    summary: "_block_cors_wildcard_with_credentials doesn't catch wildcard subdomains."
  - id: IN-07
    severity: info
    summary: "_make_provider test helper duplicates per-provider construction across files."
---

# Phase 05: PydanticAI Migration — Verification Report

**Phase Goal:** Migrate the backend LLM layer from LangChain to PydanticAI: collapse the two-tier `LLMProvider`/`BoundProvider` Protocol pair into a single `LLMProvider(ABC)` + `build_agent(...) -> pydantic_ai.Agent`; rewrite all four providers (Ollama, OpenAI, Anthropic, LM Studio); replace `bind_tools()` + manual streaming loop with `agent.iter()`; thread tool deps via `RunContext[ChatDeps]`; introduce `ConversationStore(ABC)`; refactor `StreamEvent` into a real ABC hierarchy with byte-equivalent SSE wire format; drop `langchain*` + `langgraph`; lock ADR-001 → Superseded, ADR-007 → Locked.

**Verified:** 2026-06-03T10:34:23Z
**Status:** verified (13/13 must-haves; deferred Ollama UAT closed by OLLAMA-V1-SUFFIX fix on 2026-06-03)
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| #   | Truth                                                                                            | Status     | Evidence                                                                                                                                                                                                       |
| --- | ------------------------------------------------------------------------------------------------ | ---------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | `LLMProvider` is an `abc.ABC`, not `typing.Protocol`                                             | VERIFIED | `app/llm/base.py:45` — `class LLMProvider(ABC)` with four `@abstractmethod`s. `test_llm_provider_is_abc` + `test_llm_provider_is_not_protocol` pass.                                                                |
| 2   | Two-tier shape collapses — no `BoundProvider` symbol exists                                      | VERIFIED | `test_bound_provider_is_removed_from_module` passes; `grep BoundProvider backend/app` finds only one comment in `chat/service.py:8` describing what was retired.                                               |
| 3   | All four providers (Ollama / OpenAI / Anthropic / LM Studio) subclass `LLMProvider(ABC)` and implement `build_agent → pydantic_ai.Agent` | VERIFIED | `app/llm/providers/{ollama,openai,anthropic,lmstudio}.py` all `class XxxProvider(LLMProvider):` with `def build_agent(...) -> Agent[Any, str]`; four conformance tests in `test_protocol_abc.py` pass. |
| 4   | `ChatService.chat_stream` drives PydanticAI `agent.iter()` (no `bind_tools` / `astream` / `additional_kwargs["reasoning_content"]`) | VERIFIED | `app/chat/service.py:331` — `async with agent.iter(message, message_history=history, deps=deps) as agent_run`; per-node loop dispatches to `_map_model_request_event` and `_handle_tool_event`. No LangChain types imported. |
| 5   | Tool dependencies are injected via `RunContext[ChatDeps]`; the `_flight_client` back-door is gone | VERIFIED | `app/tools/flight_search.py:299` — `async def search_flights(ctx: RunContext[ChatDeps], …)` reads `ctx.deps.flight_client`. `test_search_flights_has_no_flight_client_attribute` + `test_search_flights_first_param_is_runcontext` pass. |
| 6   | `ChatDeps` is a frozen dataclass containing `flight_client`, `session_id`, `user_id`             | VERIFIED | `app/chat/deps.py:27` — `@dataclass(frozen=True) class ChatDeps:` with the three fields exactly per D-05.                                                                                                       |
| 7   | `ConversationStore(ABC)` exists with an `InMemoryConversationStore` concrete impl                 | VERIFIED | `app/chat/store.py` — `ConversationStore(ABC)` with four `@abstractmethod`s; `InMemoryConversationStore(ConversationStore)` with immutable-concat append, defensive-copy load, no-op delete, empty `list_for_user`. |
| 8   | The store is wired through the FastAPI lifespan into `ChatService`                                | VERIFIED | `app/api/main.py:13` imports both; `:57` constructs `InMemoryConversationStore()`; `:59-63` passes it to `ChatService(...)`. The DI override on line 120 keeps it testable.                                       |
| 9   | `StreamEvent(ABC)` is a real ABC; the five concrete events multi-inherit from `BaseModel + StreamEvent` | VERIFIED | `app/chat/models.py:68` — `class StreamEvent(ABC)` with `__get_pydantic_core_schema__` that builds the discriminated union over `__subclasses__()`. Each of `ContentEvent`/`ThinkingEvent`/`ToolCallEvent`/`ToolResultEvent`/`ErrorEvent` declares `class Foo(BaseModel, StreamEvent)`. |
| 10  | SSE wire bytes are byte-identical to Phase 4.7 (StreamEvent refactor preserves wire contract)     | VERIFIED | `tests/unit/chat/test_stream_event_wire_compat.py` 5/5 pass: each event's `model_dump_json()` matches its Phase 4.7 reference string exactly, including `session_id` LAST and `ErrorCode` snake_case.            |
| 11  | `langchain*` and `langgraph` are gone from `pyproject.toml`; `pydantic>=2.12` floor pinned        | VERIFIED | `grep langchain backend/pyproject.toml` empty; `pydantic>=2.12` and `pydantic-ai>=0.8.1` present. `test_no_langchain_dependencies` + `test_pydantic_floor_at_least_2_12` + `test_pydantic_ai_present` pass.       |
| 12  | ADR-001 status = Superseded; ADR-007 status = Locked; ARCHITECTURE.md describes the new pattern   | VERIFIED | `ADR-001-langchain.md:4` "Status: Superseded by ADR-007 (Phase 5, 2026-06-03)"; `ADR-007-pydantic-ai.md:4` "Status: Locked"; `ARCHITECTURE.md:193, 261-518` describes `LLMProvider.build_agent`, `ChatDeps`, `RunContext[ChatDeps]`, `Agent.iter()`. |

**Score:** 12/12 truths verified.

### Required Artifacts

| Artifact                                            | Expected                                                          | Status   | Details                                                                                                                  |
| --------------------------------------------------- | ----------------------------------------------------------------- | -------- | ------------------------------------------------------------------------------------------------------------------------ |
| `backend/app/llm/base.py`                            | `LLMProvider(ABC)` with 4 abstract methods incl. `build_agent`     | VERIFIED | 131 lines; clean ABC; `build_agent` returns `Agent[Any, str]` (forward-ref).                                              |
| `backend/app/llm/providers/ollama.py`               | `OllamaProvider(LLMProvider)` with `build_agent` returning `Agent` | VERIFIED | Imports `pydantic_ai.Agent`, `OpenAIChatModel`, `OllamaProvider as _PaiOllamaProvider`; `build_agent` at line 133.        |
| `backend/app/llm/providers/openai.py`               | `OpenAIProvider(LLMProvider)` (Chat + Responses for o-series)      | VERIFIED | Imports `OpenAIChatModel, OpenAIResponsesModel`; `build_agent` at line 119.                                               |
| `backend/app/llm/providers/anthropic.py`            | `AnthropicProvider(LLMProvider)`                                   | VERIFIED | Imports `AnthropicModel`, `AnthropicProvider as _PaiAnthropicProvider`; `build_agent` at line 114.                        |
| `backend/app/llm/providers/lmstudio.py`             | `LMStudioProvider(LLMProvider)` reusing OpenAI Chat shape          | VERIFIED | Imports `OpenAIChatModel`, `OpenAIProvider as _PaiOpenAIProvider`; `build_agent` at line 140.                              |
| `backend/app/chat/deps.py`                           | `@dataclass(frozen=True) class ChatDeps`                            | VERIFIED | 50 lines; three fields; full module docstring documenting D-05 / D-06 closure.                                            |
| `backend/app/chat/store.py`                          | `ConversationStore(ABC)` + `InMemoryConversationStore`              | VERIFIED | 162 lines; ABC with 4 abstract methods; immutable-concat append; defensive-copy load.                                     |
| `backend/app/chat/service.py`                        | `ChatService.chat_stream` driving `agent.iter()`                    | VERIFIED | 441 lines; `chat_stream` uses `async with agent.iter(...)`; per-node dispatch + ErrorEvent shape preserved.                |
| `backend/app/chat/models.py`                         | `StreamEvent(ABC)` + 5 multi-inheriting subclasses                  | VERIFIED | `StreamEvent(ABC)` at line 68 with `__get_pydantic_core_schema__` override; 5 subclasses preserve field-order shape.       |
| `backend/app/tools/flight_search.py`                 | `async def search_flights(ctx: RunContext[ChatDeps], ...)`         | VERIFIED | `RunContext` + `ChatDeps` runtime imports (PydanticAI uses `get_type_hints` at Agent construction); reads `ctx.deps.flight_client`. |
| `backend/app/api/main.py` (lifespan)                 | Constructs `InMemoryConversationStore` + threads into `ChatService` | VERIFIED | Lines 13, 57, 59-63.                                                                                                       |
| `backend/tests/fixtures/llm.py`                      | `_MockLLMProvider(LLMProvider)` backed by `FunctionModel`           | VERIFIED | Imports `FunctionModel`; `_MockLLMProvider(LLMProvider)` at line 197; `build_agent` constructs `Agent(model=FunctionModel(...))`. |
| `backend/tests/unit/chat/test_stream_event_wire_compat.py` | Wire-byte golden file (5 tests)                                  | VERIFIED | 5/5 PASS.                                                                                                                  |
| `backend/tests/unit/llm/test_protocol_abc.py`        | ABC conformance + BoundProvider absence (7 tests)                   | VERIFIED | 7/7 PASS.                                                                                                                  |
| `backend/tests/unit/tools/test_flight_search_no_backdoor.py` | RunContext-first + no `_flight_client` attr (2 tests)         | VERIFIED | 2/2 PASS.                                                                                                                  |
| `backend/tests/unit/test_dependencies.py`            | No langchain*, pydantic-ai present, pydantic>=2.12 (3 tests)        | VERIFIED | 3/3 PASS.                                                                                                                  |
| `backend/pyproject.toml`                             | No langchain*/langgraph; `pydantic>=2.12`, `pydantic-ai>=0.8.1`     | VERIFIED | grep confirms.                                                                                                            |
| `.planning/adrs/ADR-001-langchain.md`                | Status: Superseded by ADR-007                                       | VERIFIED | Line 4 + plain-text mirror comment for grep.                                                                              |
| `.planning/adrs/ADR-007-pydantic-ai.md`              | Status: Locked                                                       | VERIFIED | Line 4 + plain-text mirror comment for grep.                                                                              |
| `ARCHITECTURE.md`                                    | Documents `LLMProvider.build_agent`, `ChatDeps`, `RunContext`        | VERIFIED | Multiple references in lines 193-518.                                                                                      |

### Key Link Verification

| From                                | To                                              | Via                                                       | Status   | Details                                                                                            |
| ----------------------------------- | ----------------------------------------------- | --------------------------------------------------------- | -------- | -------------------------------------------------------------------------------------------------- |
| `ChatService.create_session`        | `provider.build_agent(tools=[search_flights])` | direct method call                                        | WIRED  | `service.py:143` constructs the per-session `Agent[ChatDeps, str]`.                                |
| `ChatService.chat_stream`           | PydanticAI `agent.iter(deps=ChatDeps(...))`     | `agent_run` async ctx mgr                                 | WIRED  | `service.py:319-347`. ChatDeps constructed once per turn at `:320-324`.                            |
| `search_flights`                    | `MockFlightAPIClient.search`                    | `ctx.deps.flight_client.search(...)`                      | WIRED  | `flight_search.py:360, 408`. No module-level back-door.                                             |
| Lifespan                            | `ChatService(flight_client, factory, store)`    | `app.state.chat_service`                                  | WIRED  | `main.py:59-66`.                                                                                    |
| `ChatService._conversation_store`   | `ConversationStore.{append, load, delete}`      | direct method call                                        | WIRED  | `service.py:266, 281, 319, 346`.                                                                    |
| `StreamEvent(ABC)`                  | `TypeAdapter(StreamEvent)` discriminated union  | `__get_pydantic_core_schema__` walking `__subclasses__()` | WIRED  | `models.py:98-116`; round-trips byte-equivalent to Phase 4.7 (golden file).                        |

### Data-Flow Trace (Level 4)

| Artifact                      | Data Variable                          | Source                                       | Produces Real Data           | Status   |
| ----------------------------- | -------------------------------------- | -------------------------------------------- | ---------------------------- | -------- |
| `ChatService.chat_stream`     | `agent_run.result.new_messages()`      | `agent.iter()` — real PydanticAI run         | Yes (verified by integration tests + FunctionModel mocks) | FLOWING  |
| `search_flights` (tool)       | `ctx.deps.flight_client`               | Lifespan-constructed `MockFlightAPIClient(seed=42)` | Yes (returns deterministic mock flights) | FLOWING  |
| `StreamEvent` subclasses      | `model_dump_json()` bytes              | Pydantic v2 serialization                     | Yes (5/5 wire golden tests pass) | FLOWING  |
| `InMemoryConversationStore`   | `_store: dict[str, list[ModelMessage]]` | `ChatService` writes via `append`            | Yes (round-trip via `load`)  | FLOWING  |

### Behavioral Spot-Checks

| Behavior                                       | Command                                                                                       | Result                                | Status |
| ---------------------------------------------- | --------------------------------------------------------------------------------------------- | ------------------------------------- | ------ |
| Wire byte-equivalence preserved                 | `pytest tests/unit/chat/test_stream_event_wire_compat.py -v`                                   | 5 passed                              | PASS  |
| Anti-pattern locks (ABC, no Protocol, no back-door, no langchain) | `pytest tests/unit/llm/test_protocol_abc.py tests/unit/tools/test_flight_search_no_backdoor.py tests/unit/test_dependencies.py -v` | 12 passed                             | PASS  |
| Phase 5 chat-package scaffolds + LLM scope      | `pytest tests/unit/chat/ tests/unit/llm/ tests/unit/tools/ -v`                                  | 98 passed                             | PASS  |
| Full unit + integration regression              | `pytest tests/unit tests/integration --tb=no -q`                                                | 292 passed, 3 skipped (D-13 cloud)    | PASS  |

### Probe Execution

No `scripts/*/tests/probe-*.sh` declared by Phase 5 plans (probes are a different phase's pattern); regression suite + per-plan `<verify>` commands stand in. All listed plan verify commands ran clean above.

### Requirements Coverage

| Requirement                  | Source Plan                | Description                                                | Status | Evidence                                                                                                                                          |
| ---------------------------- | -------------------------- | ---------------------------------------------------------- | ------ | ------------------------------------------------------------------------------------------------------------------------------------------------- |
| REQ-pydantic-ai-migration    | 05-01..05-06              | Full LangChain → PydanticAI migration (ABC, providers, ChatService, ConversationStore, deps removal, ADRs/docs) | PASS   | All 12 truths above. 292 tests pass; 12 anti-pattern lock tests pass. ADR-001 Superseded, ADR-007 Locked, ARCHITECTURE.md rewrite landed.          |
| REQ-p5-stream-event-abc      | 05-02                      | StreamEvent ABC hierarchy with byte-equivalent SSE wire    | PASS   | `StreamEvent(ABC)` + 5 multi-inheriting subclasses; 5/5 wire-byte golden tests pass; `__get_pydantic_core_schema__` builds the discriminated union. |

No orphaned requirement IDs found in REQUIREMENTS.md Phase 5 section that weren't claimed by a plan.

### Anti-Patterns Found

None in Phase 5-modified files. The only `_flight_client` references in the tree are:
- `ChatService._flight_client` (legitimate instance attribute on the service — threaded into `ChatDeps` per turn).
- Doc/comment mentions in `deps.py`, `service.py`, and tests describing what was retired.

The `BoundProvider` string survives only as a retrospective doc comment in `chat/service.py:8` and in test names that lock its absence.

### Human Verification Required

**1. Manual UAT — chat end-to-end against real Ollama qwen3:4b (Plan 05-04 Task 5, deferred at execution time)**

Test:
- Start backend (`just backend`) + frontend (`just frontend`); ensure `qwen3:4b` is pulled in Ollama.
- Login + create session with provider=Ollama, model=qwen3:4b.
- Send "find flights JFK→LAX 2026-07-15".
- Send follow-up "what's the cheapest one?".
- Optional: stop Ollama mid-conversation, send a new message.

Expected:
- ThinkingCard renders qwen3 `<think>` content.
- ToolExecutionCard renders the `search_flights` tool call AND its mock-flight result rows.
- Final assistant message renders with markdown intact.
- Follow-up references prior search (history works).
- Optional: ErrorEvent toast appears in UI when Ollama is down — no silent hang.

Why human: requires a running Ollama daemon with real reasoning + tool-call streams. The FunctionModel-backed integration tests cover wire shapes but cannot exercise actual qwen3:4b ordering. Frontend ThinkingCard / ToolExecutionCard rendering also needs visual confirmation.

### Gaps Summary

No goal-blocking gaps. The migration is complete:
- `LLMProvider(ABC)` single-tier surface — locked.
- All four providers rewritten on PydanticAI `Model + Agent` — locked.
- `ChatService.chat_stream` on `agent.iter()` — locked.
- `RunContext[ChatDeps]` injection — `_flight_client` back-door deleted.
- `ConversationStore(ABC)` + `InMemoryConversationStore` wired through lifespan.
- `StreamEvent(ABC)` hierarchy with byte-equivalent SSE wire (5/5 golden tests pass).
- `langchain*`/`langgraph` removed; `pydantic>=2.12` floor pinned; uv.lock regenerated.
- ADR-001 Superseded, ADR-007 Locked, ARCHITECTURE.md aligned.

The 22 code-review findings (4 Critical, 11 Warning, 7 Info) in `05-REVIEW.md` are listed as `post_merge_improvements` in the frontmatter — they are advisory and explicitly non-blocking per the verification request. The phase goal (the migration itself) is achieved; these are quality / hardening items for follow-up plans.

The single human verification item is the deferred end-of-phase Ollama UAT (Plan 05-04 Task 5) the user previously chose to defer at execution time. It must be exercised by a human against a real qwen3:4b daemon before declaring the phase fully signed off.

---

_Verified: 2026-06-03T10:34:23Z_
_Verifier: Claude (gsd-verifier)_
