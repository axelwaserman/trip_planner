---
phase: 05-pydanticai-migration
verified: 2026-06-27T00:00:00Z
status: pass
score: 7/7 must-haves verified
overrides_applied: 0
re_verification:
  previous_status: gaps_found
  previous_score: 6/7
  gaps_closed:
    - "LLMProvider is abc.ABC — verified"
    - "ChatService uses PydanticAI agent.iter() — verified"
    - "StreamEvent ABC hierarchy — verified"
    - "langchain* absent from pyproject.toml — verified"
    - "search_flights uses RunContext[ChatDeps] — verified"
    - "SSE wire contract preserved — verified"
    - "Tests pass — fixed: conftest.py updated to stub pyreqwest ClientBuilder; hardcoded 2026-06-15 dates advanced to 2030-06-15 in test fixtures. 295 passed, 3 skipped, 0 failed (commit 8e63c3d)."
  gaps_remaining: []
  regressions: []
requirements:
  - id: REQ-pydantic-ai-migration
    status: PASS
    evidence: "All structural migration goals met. 295 unit+integration tests pass (3 skipped). Anti-pattern lock tests 17/17 pass. conftest.py updated to pyreqwest stubs (commit 8e63c3d)."
  - id: REQ-p5-stream-event-abc
    status: PASS
    evidence: "StreamEvent(ABC) marker class with __get_pydantic_core_schema__ override at app/chat/models.py:68-116; five concrete subclasses; test_stream_event_wire_compat.py 5/5 passes."
gaps: []
    reason: "Plan 05-07 Task 4 (commit f9b610e) migrated OllamaProvider and LMStudioProvider from httpx to pyreqwest (ADR-008 compliance). The integration test conftest at tests/integration/conftest.py was not updated — it still patches httpx.AsyncClient.get. All tests that call POST /api/chat/session receive 502 Bad Gateway (PROVIDER_UNREACHABLE) instead of 201. Additionally, MockLLMStream.single_tool_call() hardcodes departure_date='2026-06-15' which is now in the past, triggering FlightQuery.validate_departure_not_in_past and causing 4 tests to fail (3 unit + 1 integration). These are distinct root causes."
    artifacts:
      - path: "backend/tests/integration/conftest.py"
        issue: "autouse fixture patches httpx.AsyncClient.get but OllamaProvider and LMStudioProvider now use pyreqwest.ClientBuilder. The mock never intercepts the probe call."
      - path: "backend/tests/fixtures/llm.py"
        issue: "MockLLMStream.single_tool_call() hardcodes departure_date='2026-06-15' — now in the past. FlightQuery.validate_departure_not_in_past rejects it."
      - path: "backend/tests/unit/test_tool_json_normalization.py"
        issue: "Three tests use FlightQuery with departure_date=date(2026, 6, 15) which is now in the past."
    missing:
      - "Update tests/integration/conftest.py autouse fixture to stub pyreqwest instead of (or in addition to) httpx — patch pyreqwest.client.ClientBuilder or the relevant pyreqwest send method so the Ollama /api/tags call returns the mock tags response."
      - "Update MockLLMStream.single_tool_call() default departure_date to a future date (e.g., a relative date using datetime.now() + timedelta(days=30)) to avoid the FlightQuery past-date guard."
      - "Update test_tool_json_normalization.py fixture dates similarly."
human_verification:
  - test: "Manual UAT — chat end-to-end against real Ollama qwen3:4b"
    expected: |
      With `just backend` + `just frontend` running and `qwen3:4b` pulled in Ollama:
      1. Login + session create with provider=Ollama, model=qwen3:4b succeeds.
      2. Prompt "find flights JFK→LAX 2026-07-15" produces a ThinkingCard, ToolExecutionCard for search_flights with mock-flight rows, and a final assistant message.
      3. Follow-up "what's the cheapest one?" references prior turn.
      4. (Optional) Stop Ollama mid-conversation → frontend renders ErrorEvent toast.
    why_human: "Requires a live Ollama daemon with qwen3:4b. FunctionModel integration tests cover wire shapes but cannot exercise real reasoning + tool-call ordering. Visual ThinkingCard/ToolExecutionCard rendering needs confirmation."
---

# Phase 05: PydanticAI Migration — Verification Report (Re-verification)

**Phase Goal:** Migrate backend LLM layer from LangChain to PydanticAI: `LLMProvider(ABC)` + `build_agent`; rewrite four providers; replace `bind_tools()` + manual streaming with `agent.iter()`; thread tool deps via `RunContext[ChatDeps]`; `ConversationStore(ABC)`; `StreamEvent` ABC hierarchy; drop `langchain*`; lock ADR-001 → Superseded, ADR-007 → Locked.

**Verified:** 2026-06-27T00:00:00Z
**Status:** gaps_found
**Re-verification:** Yes — after Plan 05-07 post-review fixes (completed 2026-06-21)

---

## Goal Achievement

### Observable Truths

| #   | Truth                                                                                            | Status      | Evidence                                                                                                                                                 |
| --- | ------------------------------------------------------------------------------------------------ | ----------- | -------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | `ChatService` uses PydanticAI `Agent` — no LangChain imports in `app/chat/` or `app/llm/`       | VERIFIED  | `service.py` imports from `pydantic_ai.*` only; `from pydantic_ai import Agent` at line 32. No `langchain` in `app/chat/` or `app/llm/`.               |
| 2   | `LLMProvider` is `abc.ABC`, not `typing.Protocol`                                               | VERIFIED  | `app/llm/base.py:45` — `class LLMProvider(ABC)` with four `@abstractmethod`s. `test_llm_provider_is_abc` + `test_llm_provider_is_not_protocol` pass.  |
| 3   | SSE wire contract preserved: five `StreamEvent` subclasses still emitted                         | VERIFIED  | `ContentEvent`, `ThinkingEvent`, `ToolCallEvent`, `ToolResultEvent`, `ErrorEvent` in `models.py`. Wire golden tests 5/5 pass.                            |
| 4   | `langchain*` packages absent from `backend/pyproject.toml` dependencies                          | VERIFIED  | `grep langchain backend/pyproject.toml` — empty. `pydantic-ai>=0.8.1` present. `test_no_langchain_dependencies` passes.                                  |
| 5   | `search_flights` tool uses PydanticAI `RunContext` deps, not `._flight_client` attribute         | VERIFIED  | `flight_search.py:299` — `async def search_flights(ctx: RunContext[ChatDeps], ...)` reads `ctx.deps.flight_client`. Backdoor tests 2/2 pass.             |
| 6   | `StreamEvent` is an ABC hierarchy, not a `Literal` union alias                                   | VERIFIED  | `models.py:68` — `class StreamEvent(ABC)` with `__get_pydantic_core_schema__`. Five subclasses multi-inherit `(BaseModel, StreamEvent)`.                |
| 7   | Tests pass (unit + integration; pre-existing failures excluded)                                   | FAILED    | 22 integration tests fail (502 on session creation — pyreqwest probe not mocked in conftest). 4 tests fail from hardcoded past dates in fixtures. See Gaps. |

**Score:** 6/7 truths verified.

---

### Required Artifacts

| Artifact                                            | Expected                                                          | Status   | Details                                                                     |
| --------------------------------------------------- | ----------------------------------------------------------------- | -------- | --------------------------------------------------------------------------- |
| `backend/app/llm/base.py`                           | `LLMProvider(ABC)` with 4 abstract methods incl. `build_agent`   | VERIFIED | 131 lines; clean ABC; `build_agent` returns `Agent[Any, str]`.              |
| `backend/app/llm/providers/ollama.py`               | `OllamaProvider(LLMProvider)` using pyreqwest + `build_agent`    | VERIFIED | Uses `pyreqwest.ClientBuilder`; `build_agent` returns PydanticAI `Agent`.   |
| `backend/app/llm/providers/openai.py`               | `OpenAIProvider(LLMProvider)` with explicit ValueError guard      | VERIFIED | `assert` replaced with `ValueError`; `build_agent` at line 119.             |
| `backend/app/llm/providers/anthropic.py`            | `AnthropicProvider(LLMProvider)` with explicit ValueError guard   | VERIFIED | `assert` replaced with `ValueError`; `build_agent` at line 114.             |
| `backend/app/llm/providers/lmstudio.py`             | `LMStudioProvider(LLMProvider)` using pyreqwest + `build_agent`  | VERIFIED | Uses `pyreqwest.ClientBuilder`; `build_agent` at line 140.                  |
| `backend/app/chat/deps.py`                          | `@dataclass(frozen=True) class ChatDeps`                          | VERIFIED | 50 lines; three fields.                                                     |
| `backend/app/chat/store.py`                         | `ConversationStore(ABC)` + `InMemoryConversationStore`            | VERIFIED | 162 lines; ABC with 4 abstract methods.                                     |
| `backend/app/chat/service.py`                       | `ChatService.chat_stream` driving `agent.iter()`                  | VERIFIED | 508 lines; `async with agent.iter(...)`; TOCTOU KeyError guard; RetryPromptPart branch. |
| `backend/app/chat/models.py`                        | `StreamEvent(ABC)` + 5 multi-inheriting subclasses                | VERIFIED | `StreamEvent(ABC)` at line 68; 5 subclasses; `ChatRequest.message` max_length=32_768. |
| `backend/app/tools/flight_search.py`                | `async def search_flights(ctx: RunContext[ChatDeps], ...)`        | VERIFIED | `RunContext` + `ChatDeps` runtime imports; reads `ctx.deps.flight_client`.  |
| `backend/app/api/main.py` (lifespan)                | Constructs `InMemoryConversationStore` + threads into `ChatService` | VERIFIED | Lines 13, 57, 59-63.                                                        |
| `backend/tests/fixtures/llm.py`                     | `_MockLLMProvider(LLMProvider)` backed by `FunctionModel`         | VERIFIED | `_MockLLMProvider(LLMProvider)` at line 197; `build_agent` constructs `Agent(model=FunctionModel(...))`. |
| `backend/tests/integration/conftest.py`             | Stubs pyreqwest probe for session creation in integration tests   | STUB     | Still stubs `httpx.AsyncClient.get`. Providers now use pyreqwest — stub is ineffective. 22 integration tests fail as a result. |

---

### Key Link Verification

| From                                | To                                              | Via                                                       | Status   | Details                                                             |
| ----------------------------------- | ----------------------------------------------- | --------------------------------------------------------- | -------- | ------------------------------------------------------------------- |
| `ChatService.create_session`        | `provider.build_agent(tools=[search_flights])`  | direct method call                                        | WIRED  | `service.py:144` constructs per-session `Agent[ChatDeps, str]`.     |
| `ChatService.chat_stream`           | PydanticAI `agent.iter(deps=ChatDeps(...))`     | `agent_run` async ctx mgr                                 | WIRED  | `service.py:381`; ChatDeps constructed at line 365-369.             |
| `search_flights`                    | `MockFlightAPIClient.search`                    | `ctx.deps.flight_client.search(...)`                      | WIRED  | `flight_search.py:412`. No module-level back-door.                  |
| Lifespan                            | `ChatService(flight_client, factory, store)`    | `app.state.chat_service`                                  | WIRED  | `main.py:59-66`.                                                    |
| `OllamaProvider.validate_config`    | pyreqwest `ClientBuilder` → `/api/tags`         | `pyreqwest.client.ClientBuilder`                          | WIRED  | `ollama.py:128-131`. httpx removed.                                 |
| `tests/integration/conftest.py`     | pyreqwest `/api/tags` stub                      | monkeypatch pyreqwest                                     | NOT_WIRED | Still patches `httpx.AsyncClient.get` — pyreqwest calls are not intercepted. |

---

### Data-Flow Trace (Level 4)

| Artifact                     | Data Variable                    | Source                                        | Produces Real Data                            | Status      |
| ---------------------------- | -------------------------------- | --------------------------------------------- | --------------------------------------------- | ----------- |
| `ChatService.chat_stream`    | `agent_run.result.new_messages()` | `agent.iter()` — real PydanticAI run          | Yes (verified by FunctionModel integration tests) | FLOWING   |
| `search_flights` (tool)      | `ctx.deps.flight_client`          | Lifespan-constructed `MockFlightAPIClient`    | Yes (deterministic mock flights)              | FLOWING   |
| `StreamEvent` subclasses     | `model_dump_json()` bytes         | Pydantic v2 serialization                     | Yes (5/5 wire golden tests pass)              | FLOWING   |
| `InMemoryConversationStore`  | `_store: dict[str, list[...]]`   | `ChatService` writes via `append`             | Yes (round-trip via `load`)                   | FLOWING   |

---

### Behavioral Spot-Checks

| Behavior                                                                                    | Command                                                                                         | Result                                                | Status    |
| ------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------- | ----------------------------------------------------- | --------- |
| Wire byte-equivalence preserved                                                             | `pytest tests/unit/chat/test_stream_event_wire_compat.py -v`                                    | 5 passed                                              | PASS    |
| Anti-pattern locks (ABC, no Protocol, no back-door, no langchain)                           | `pytest tests/unit/llm/test_protocol_abc.py tests/unit/tools/test_flight_search_no_backdoor.py tests/unit/test_dependencies.py -v` | 12 passed                            | PASS    |
| Full unit suite                                                                             | `pytest tests/unit --tb=no -q`                                                                  | 237 passed, 3 failed (hardcoded past dates — pre-existing) | PARTIAL |
| Full integration suite                                                                      | `pytest tests/integration --tb=no -q`                                                           | 33 passed, 22 failed, 3 skipped (pyreqwest stub missing) | FAIL  |

---

### Probe Execution

No `scripts/*/tests/probe-*.sh` declared by Phase 5 plans. Regression suite is the verification mechanism.

---

### Requirements Coverage

| Requirement               | Source Plan     | Description                                                                                 | Status  | Evidence                                                                                                                    |
| ------------------------- | --------------- | ------------------------------------------------------------------------------------------- | ------- | --------------------------------------------------------------------------------------------------------------------------- |
| REQ-pydantic-ai-migration | 05-01..05-07    | Full LangChain → PydanticAI migration (ABC, providers, ChatService, ConversationStore, deps removal, ADRs/docs, security fixes) | PARTIAL | All structural goals met. Integration test suite partially broken (22 tests) due to conftest not updated after httpx→pyreqwest migration. |
| REQ-p5-stream-event-abc   | 05-02           | StreamEvent ABC hierarchy with byte-equivalent SSE wire                                     | PASS    | `StreamEvent(ABC)` + 5 multi-inheriting subclasses; 5/5 wire-byte golden tests pass.                                        |

---

### Anti-Patterns Found

| File                                    | Line  | Pattern                                                              | Severity    | Impact                                                                                       |
| --------------------------------------- | ----- | -------------------------------------------------------------------- | ----------- | -------------------------------------------------------------------------------------------- |
| `tests/integration/conftest.py`         | 67-70 | `monkeypatch.setattr(httpx.AsyncClient, "get", ...)` — stubs wrong library after pyreqwest migration | BLOCKER | 22 integration tests fail (502 on session creation). |
| `tests/fixtures/llm.py`                 | 118   | `"departure_date": "2026-06-15"` hardcoded past date in MockLLMStream.single_tool_call() | BLOCKER | 1 integration test fails (FlightQuery validator rejects past dates). |
| `tests/unit/test_tool_json_normalization.py` | multiple | `departure_date=date(2026, 6, 15)` hardcoded past date          | BLOCKER | 3 unit tests fail (FlightQuery validator rejects past dates).                                 |

---

### Human Verification Required

**1. Manual UAT — chat end-to-end against real Ollama qwen3:4b**

**Test:** Start backend (`just backend`) + frontend (`just frontend`); ensure `qwen3:4b` is pulled in Ollama.
- Login + create session with provider=Ollama, model=qwen3:4b.
- Send "find flights JFK→LAX 2026-07-15".
- Send follow-up "what's the cheapest one?".
- Optional: stop Ollama mid-conversation, send a new message.

**Expected:**
- ThinkingCard renders qwen3 `<think>` content.
- ToolExecutionCard renders the `search_flights` tool call AND its mock-flight result rows.
- Final assistant message renders with markdown intact.
- Follow-up references prior search (history works).
- Optional: ErrorEvent toast appears in UI when Ollama is down — no silent hang.

**Why human:** Requires a running Ollama daemon with real reasoning + tool-call streams. The FunctionModel-backed integration tests cover wire shapes but cannot exercise actual qwen3:4b ordering. Frontend ThinkingCard / ToolExecutionCard rendering also needs visual confirmation.

---

### Gaps Resolution (2026-06-27)

Both previously identified gaps are now **closed** (commit `8e63c3d`):

**Root Cause 1 — RESOLVED:** `tests/integration/conftest.py` updated to stub `pyreqwest.ClientBuilder` instead of `httpx.AsyncClient.get`. The autouse fixture now patches the full call chain (`ClientBuilder → Client → RequestBuilder → Request → Response`) returning correct Ollama `/api/tags` + LM Studio `/v1/models` payloads. `test_session_probe.py` fully rewritten to use pyreqwest mocks.

**Root Cause 2 — RESOLVED:** Hardcoded `2026-06-15` dates advanced to `2030-06-15` in `tests/fixtures/llm.py`, `tests/unit/test_tool_json_normalization.py`, and `tests/integration/test_chat.py`.

**Final test result:** 295 passed, 3 skipped, 0 failed.

---

## Final Verdict: ✓ PASS

All 7 must-haves verified. Phase 05 goal achieved.

---

_Verified: 2026-06-27T00:00:00Z_
_Verifier: Claude_
