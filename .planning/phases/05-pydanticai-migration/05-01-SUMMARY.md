---
phase: 05-pydanticai-migration
plan: 01
subsystem: testing
tags: [pytest, tdd, scaffolding, pydantic-ai, langchain-removal, wire-compat, anti-pattern-lock]

# Dependency graph
requires:
  - phase: 04-7-stream-events
    provides: Phase 4.7 StreamEvent discriminated-union wire format (the golden bytes captured here)
provides:
  - Wave 0 RED test scaffolds (16 test files + 4 __init__.py markers, 20 files total)
  - Phase 4.7 SSE wire-format golden file (5 byte-equivalent assertions)
  - Anti-pattern regression locks (_flight_client back-door, BoundProvider two-tier)
  - pyproject.toml + AST-walk canaries for langchain* removal (D-20)
  - Gated cloud-acceptance skeletons for D-13 thinking-event surfaces
affects: [05-02-llm-base, 05-03-chat-store-deps, 05-04-providers-rewrite, 05-05-chat-service-rewrite, 05-06-dep-swap]

# Tech tracking
tech-stack:
  added:
    - pytest.importorskip — module-level deferral pattern for not-yet-existing imports
    - tomllib (stdlib, py3.11+) — pyproject.toml manifest reads
  patterns:
    - "Wave 0 RED stub via pytest.importorskip: collection succeeds today; tests turn RED once production code lands; turn GREEN as the implementation completes."
    - "Wire-format golden file: capture model_dump_json() bytes BEFORE any refactor; pin them in tests so byte-equivalence assertions fail loudly if the refactor regresses the contract."
    - "Anti-pattern regression lock: a test that asserts a specific BAD pattern is absent (no module attribute, no module-name, no Protocol metaclass). Becomes a project-life-of regression guard."
    - "Gated cloud acceptance: pytest.mark.skipif(not os.getenv(KEY), reason=…) at module level. Test runs end-to-end only when the corresponding API key is present; default PR CI skips."

key-files:
  created:
    - backend/tests/unit/chat/test_stream_event_wire_compat.py — 5 wire-byte golden assertions
    - backend/tests/unit/chat/test_deps.py — ChatDeps frozen dataclass shape
    - backend/tests/unit/chat/test_conversation_store.py — ConversationStore ABC + InMemory round-trip
    - backend/tests/unit/chat/test_stream_event_abc.py — StreamEvent(BaseModel, ABC) golden test
    - backend/tests/unit/chat/test_stream_event_extraction.py — agent.iter() event-loop mapping
    - backend/tests/unit/chat/test_stream_error_event.py — exception → ErrorEvent(_scrub) invariant
    - backend/tests/unit/llm/test_protocol_abc.py — LLMProvider ABC conformance + BoundProvider absent
    - backend/tests/unit/llm/test_build_agent.py — provider.build_agent → pydantic_ai.Agent
    - backend/tests/unit/llm/providers/test_openai_dispatch.py — D-14 o-series dispatch
    - backend/tests/unit/llm/providers/test_ollama_thinking.py — qwen3 thinking_tags inheritance
    - backend/tests/unit/tools/test_flight_search_no_backdoor.py — D-06 anti-pattern lock
    - backend/tests/unit/test_dependencies.py — pyproject.toml manifest canary (D-20 / Pitfall 8 / Pitfall 9)
    - backend/tests/unit/test_no_langchain_imports.py — AST-walk canary
    - backend/tests/integration/llm/test_ollama_thinking_live.py — D-13 gated acceptance
    - backend/tests/integration/llm/test_openai_thinking_live.py — D-13 gated acceptance
    - backend/tests/integration/llm/test_anthropic_thinking_live.py — D-13 gated acceptance
    - backend/tests/unit/chat/__init__.py
    - backend/tests/unit/tools/__init__.py
    - backend/tests/unit/llm/providers/__init__.py
    - backend/tests/integration/llm/__init__.py
  modified: []

key-decisions:
  - "Use pytest.importorskip at module level for Wave 0 stubs. Avoids ImportError in --collect-only when modules / packages don't exist yet; turns into a real RED test once imports resolve in later waves."
  - "Capture wire-format golden bytes by invoking the live Phase 4.7 production classes once during plan execution and recording the literal output strings into the test file. The bytes ARE the Phase 4.7 reference — no mock or shim required."
  - "Anti-pattern locks (no _flight_client, no BoundProvider, no langchain* import) are written as direct assertions, not skipped scaffolds. They run on every test run and will fail loudly if a future commit re-introduces the anti-pattern, even years later."

patterns-established:
  - "Wave 0 RED scaffold pattern: every later-wave production module gets a test stub on the day the plan starts; pytest.importorskip lets collection succeed; --collect-only is the verification gate."
  - "Wire-byte golden file: pin the SSE contract before any refactor, so the refactor is allowed to merge ONLY if the bytes are byte-equivalent (RESEARCH OQ-01 verification)."

requirements-completed: []  # REQ-pydantic-ai-migration and REQ-p5-stream-event-abc are advanced (not completed) by this plan; full completion lands in Wave 5+ when production code matches the scaffolds.

# Metrics
duration: 12min
completed: 2026-06-03
---

# Phase 5 Plan 01: Wave 0 Test Scaffolds Summary

**18 RED test files (plus 4 `__init__.py` markers) seeded for the LangChain → PydanticAI rewrite, with byte-equivalent SSE wire-format golden bytes captured before any refactor lands.**

## Performance

- **Duration:** ~12 min (capture-time approximate; per-task commits at 2026-06-03T11:57:46+07:00, 12:00:23, 12:01:53, 12:04:52)
- **Started:** 2026-06-03T11:55:00+07:00 (approx — plan-execution start)
- **Completed:** 2026-06-03T12:05:00+07:00
- **Tasks:** 4 (all auto, none paused at checkpoints)
- **Files created:** 20 (16 test files + 4 `__init__.py` package markers)
- **Files modified:** 0 (no production-code changes — pure Wave 0 scaffolding)

## Accomplishments

- **Phase 4.7 wire-format golden bytes captured** (Task 1, commit `bd30b8f`). Five `model_dump_json()` strings (one per concrete `StreamEvent` subclass) pinned verbatim so the Wave 1 ABC refactor can land only if it preserves byte-equivalence (D-15 / RESEARCH OQ-01). The golden file is the only Wave 0 test that passes today; it must stay green for the rest of the project.
- **Five chat-package RED stubs** seeded for Wave 1 (Task 2, commit `2569f6a`): `ChatDeps` shape, `ConversationStore` ABC + `InMemoryConversationStore` round-trip, `StreamEvent(BaseModel, ABC)` golden, `agent.iter()` event-mapping, exception → `ErrorEvent(_scrub)` invariant.
- **Four llm-package RED stubs** seeded for Wave 1 + Wave 2 + Wave 4 (Task 3, commit `af17ef6`): ABC conformance + `BoundProvider`-removed regression guard, `provider.build_agent` per provider, `OpenAIResponsesModel` o-series dispatch, qwen3 `thinking_tags` inheritance.
- **Eight tools + manifest + import-scan + live-acceptance stubs** (Task 4, commit `c1e15c0`): `_flight_client` back-door anti-pattern lock, three `pyproject.toml` canaries (no langchain*, pydantic-ai present, pydantic floor >= 2.12 — Pitfall 8 / Pitfall 9), AST-walk import scanner, three D-13 gated cloud-acceptance skeletons (Ollama / OpenAI / Anthropic).
- **Verification: 84 tests collect cleanly across the entire `tests/unit/chat`, `tests/unit/llm`, `tests/unit/tools`, `tests/integration/llm`, `tests/unit/test_dependencies.py`, `tests/unit/test_no_langchain_imports.py` set** (zero collection errors). The 5 wire-compat tests pass; everything else is RED-by-design until later waves land production code.

## Task Commits

Each task committed atomically:

1. **Task 1: Capture Phase 4.7 SSE wire-format golden bytes** — `bd30b8f` (test)
2. **Task 2: chat-package Wave 0 RED stubs** — `2569f6a` (test)
3. **Task 3: llm-package Wave 0 RED stubs** — `af17ef6` (test)
4. **Task 4: tools + manifest + import-scan + live-acceptance stubs** — `c1e15c0` (test)

_(No production code changed; no `feat`/`refactor` commits were emitted.)_

## Files Created

### Wire-format golden file (Task 1)

- `backend/tests/unit/chat/test_stream_event_wire_compat.py` — Five byte-equivalent `model_dump_json()` assertions, one per `StreamEvent` subclass.

### chat-package RED stubs (Task 2)

- `backend/tests/unit/chat/__init__.py` — package marker.
- `backend/tests/unit/chat/test_deps.py` — `ChatDeps` frozen-dataclass shape (D-05).
- `backend/tests/unit/chat/test_conversation_store.py` — `ConversationStore` ABC + `InMemoryConversationStore` round-trip (D-08, D-11).
- `backend/tests/unit/chat/test_stream_event_abc.py` — `StreamEvent(BaseModel, ABC)` golden (D-15 / OQ-01).
- `backend/tests/unit/chat/test_stream_event_extraction.py` — agent.iter() event-loop → `StreamEvent` mapping (D-12).
- `backend/tests/unit/chat/test_stream_error_event.py` — Exception in `stream_function` → `ErrorEvent` with `_scrub` (Phase 4.7 invariant).

### llm-package RED stubs (Task 3)

- `backend/tests/unit/llm/test_protocol_abc.py` — ABC conformance for all four concrete providers + `BoundProvider`-removed regression (D-01..D-03).
- `backend/tests/unit/llm/test_build_agent.py` — `provider.build_agent(tools, deps_type)` returns `pydantic_ai.Agent`.
- `backend/tests/unit/llm/providers/__init__.py` — package marker.
- `backend/tests/unit/llm/providers/test_openai_dispatch.py` — D-14 dispatch (`o3-mini`/`o1-mini` → `OpenAIResponsesModel`; `gpt-4o-mini` → `OpenAIChatModel`).
- `backend/tests/unit/llm/providers/test_ollama_thinking.py` — qwen3 `thinking_tags=('<think>', '</think>')` (RESEARCH OQ-04).

### tools + manifest + import-scan + live-acceptance stubs (Task 4)

- `backend/tests/unit/tools/__init__.py` — package marker.
- `backend/tests/unit/tools/test_flight_search_no_backdoor.py` — D-06 anti-pattern lock (no `_flight_client` attribute; first param is `RunContext`).
- `backend/tests/unit/test_dependencies.py` — pyproject.toml canary (no langchain*, no langgraph, pydantic-ai present, pydantic >=2.12).
- `backend/tests/unit/test_no_langchain_imports.py` — AST walk of `backend/app/**/*.py` for any `langchain*` import.
- `backend/tests/integration/llm/__init__.py` — package marker.
- `backend/tests/integration/llm/test_ollama_thinking_live.py` — D-13 gated on `OLLAMA_BASE_URL`.
- `backend/tests/integration/llm/test_openai_thinking_live.py` — D-13 gated on `OPENAI_API_KEY`.
- `backend/tests/integration/llm/test_anthropic_thinking_live.py` — D-13 gated on `ANTHROPIC_API_KEY`.

## Phase 4.7 SSE Wire-Format Golden Bytes (Recoverable Reference)

These are the literal `model_dump_json()` strings captured against the live Phase 4.7 `app.chat.models` classes. They are pinned in `backend/tests/unit/chat/test_stream_event_wire_compat.py` so the Wave 1 `StreamEvent(BaseModel, ABC)` refactor MUST preserve byte-equivalence:

```text
ContentEvent(chunk="hi", session_id="s1") →
  {"type":"content","chunk":"hi","session_id":"s1"}

ThinkingEvent(chunk="think", session_id="s1") →
  {"type":"thinking","chunk":"think","session_id":"s1"}

ToolCallEvent(tool_name="search_flights", tool_args={"origin":"LAX"}, session_id="s1") →
  {"type":"tool_call","tool_name":"search_flights","tool_args":{"origin":"LAX"},"session_id":"s1"}

ToolResultEvent(tool_name="search_flights", tool_result="ok", elapsed_ms=42, session_id="s1") →
  {"type":"tool_result","tool_name":"search_flights","tool_result":"ok","elapsed_ms":42,"session_id":"s1"}

ErrorEvent(error_code=ErrorCode.tool_error, message="boom", retryable=True,
           tool_name="search_flights", raw_detail="scrubbed", session_id="s1") →
  {"type":"error","error_code":"tool_error","message":"boom","retryable":true,
   "tool_name":"search_flights","raw_detail":"scrubbed","session_id":"s1"}
```

Field ordering reflects the Phase 4.7 model layout: each event's discriminator (`type`) first, then the event-specific fields, with `session_id` last on every concrete subclass. The Wave 1 refactor (which hoists `session_id` into a base class) MUST preserve this ordering; Pydantic v2 inheritance preserves the declared order, so no `model_config` knob should be required — but if it is, the test will catch the regression.

## Test Files in Each State After This Plan

### GREEN today (1 file, 5 tests)

- `backend/tests/unit/chat/test_stream_event_wire_compat.py` — passes against current Phase 4.7 production code.

### RED today; turn GREEN incrementally as Wave 1+ lands code

- All 8 files using `pytest.importorskip` for `app.chat.deps`, `app.chat.store`, `app.llm.base`, or `pydantic_ai` — currently SKIPPED at collection (showing "0 items / N skipped"); become real RED tests once Wave 1 creates the modules.
- `tests/unit/chat/test_stream_event_abc.py` — 4 collected RED tests against current `StreamEvent` union alias; turn GREEN after Wave 1's ABC refactor.
- `tests/unit/chat/test_stream_event_extraction.py` — 4 collected RED tests; turn GREEN after Wave 1 fixture rewrite + ChatService rewrite.
- `tests/unit/chat/test_stream_error_event.py` — 1 collected RED test; same dependency as above.
- `tests/unit/tools/test_flight_search_no_backdoor.py` — 2 collected tests; `test_search_flights_has_no_flight_client_attribute` already passes (trivially, by virtue of running outside the lifespan); `test_search_flights_first_param_is_runcontext` fails RED on `inspect.signature(StructuredTool)` — turns GREEN after Wave 1 drops the `@tool` decorator.
- `tests/unit/test_dependencies.py` — 3 collected RED tests; turn GREEN in Wave 4 (dep swap).
- `tests/unit/test_no_langchain_imports.py` — 1 collected RED test; turns GREEN in Wave 4.

### Permanently SKIPPED in default PR CI (3 files)

- All three `tests/integration/llm/test_*_thinking_live.py` skeletons. They run end-to-end only when the corresponding `*_API_KEY` / `OLLAMA_BASE_URL` env var is set.

## Decisions Made

- **`pytest.importorskip` over try/except** — produces clean SKIP output instead of bespoke pytest.skip strings, and the resulting "module skipped" status is a built-in pytest concept that surfaces in `--tb=line` reports.
- **Capture golden bytes by running the live code, not by hand-writing strings** — guarantees the recorded bytes ARE the Phase 4.7 reference. The strings are then committed verbatim into the test as literals, so the next test run does not re-derive them.
- **Anti-pattern locks live in the same directory as the production code under test** (`tests/unit/tools/test_flight_search_no_backdoor.py` next to `tools/flight_search.py`) — locks are regression guards, not migration scaffolding, so they don't move when the production code stops being a "rewrite target".

## Deviations from Plan

None — plan executed exactly as written. The plan's `<files_modified>` list (20 entries — I miscounted at 19 initially) and Task action specs were followed verbatim. The plan objective text said "18 new test files" but the `<files_modified>` enumeration plus my final commit count both show 20 (16 test files + 4 `__init__.py` markers). No production code was touched; no extra files were created.

## Issues Encountered

None.

## Self-Check: PASSED

Verified that all 20 declared files exist on disk:

- `backend/tests/unit/chat/{__init__.py,test_stream_event_wire_compat.py,test_deps.py,test_conversation_store.py,test_stream_event_abc.py,test_stream_event_extraction.py,test_stream_error_event.py}` — FOUND
- `backend/tests/unit/llm/{test_protocol_abc.py,test_build_agent.py,providers/__init__.py,providers/test_openai_dispatch.py,providers/test_ollama_thinking.py}` — FOUND
- `backend/tests/unit/tools/{__init__.py,test_flight_search_no_backdoor.py}` — FOUND
- `backend/tests/unit/{test_dependencies.py,test_no_langchain_imports.py}` — FOUND
- `backend/tests/integration/llm/{__init__.py,test_ollama_thinking_live.py,test_openai_thinking_live.py,test_anthropic_thinking_live.py}` — FOUND

Verified that all 4 task commits exist in `git log`:

- `bd30b8f` — Task 1 wire-compat — FOUND
- `2569f6a` — Task 2 chat-package — FOUND
- `af17ef6` — Task 3 llm-package — FOUND
- `c1e15c0` — Task 4 tools/manifest/integration — FOUND

Verified that wave-level `pytest --collect-only` succeeds (84 tests collected; zero collection errors).

## Next Phase Readiness

- **Wave 1** (`05-02-llm-base.md` and `05-03-chat-store-deps.md`) can now run: every Wave 1 production module has a RED test waiting for it. `pytest.importorskip` flips to real imports as soon as the modules exist.
- **Wave 4** (`05-06-dep-swap.md`) has two specific canaries (`test_dependencies.py`, `test_no_langchain_imports.py`) that gate the dep-swap merge — they are RED today, must turn GREEN before Wave 4 ships.
- **D-13 acceptance tests are in place** but currently skipped; the corresponding API keys must be set in CI to run them in a smoke pass.

---

*Phase: 05-pydanticai-migration*
*Plan: 01*
*Completed: 2026-06-03*
