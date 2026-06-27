---
phase: 05-pydanticai-migration
plan: 02
subsystem: api
tags: [pydantic-ai, abc, langchain-removal, sse, type-checking, marker-abc, immutability]

# Dependency graph
requires:
  - phase: 05-pydanticai-migration
    provides: "Wave 0 RED test scaffolds + Phase 4.7 SSE wire-format golden bytes (Plan 05-01)"
  - phase: 04-7-stream-events
    provides: "Phase 4.7 StreamEvent discriminated-union — the wire bytes the marker-ABC refactor must preserve"
provides:
  - "LLMProvider(ABC) — single-tier abstract surface (D-01..D-03); replaces the Phase 4.5 two-tier Protocol pair"
  - "ChatDeps frozen dataclass — per-turn dep container threaded through PydanticAI RunContext (D-05; closes _flight_client back-door under D-06)"
  - "ConversationStore(ABC) + InMemoryConversationStore — D-08, D-11 message-history abstraction; Phase 6 swap point"
  - "StreamEvent marker ABC — single base class for the five SSE event subclasses; TypeAdapter dispatch via __get_pydantic_core_schema__ override (D-15, D-16)"
  - "Settings.openai_o_series_model_prefixes — D-14 dispatch knob for OpenAIResponsesModel selection (Wave 2 wires it)"
  - "BoundProvider symbol eradicated from backend/app/* — anti-pattern lock honoured"
  - "app/llm/protocol.py outright deletion — pure rename + retype, no compatibility shim"
affects: [05-03-providers-rewrite, 05-04-chat-service-rewrite, 05-05-routes-deps-swap, 05-06-dep-swap]

# Tech tracking
tech-stack:
  added:
    - "abc.ABC — first-class ABC base for LLMProvider, ConversationStore, StreamEvent (replaces typing.Protocol per CLAUDE.md)"
    - "typing.TYPE_CHECKING + from __future__ import annotations — defer pydantic_ai imports until Wave 4 lands the dep"
  patterns:
    - "Marker ABC (pure abc.ABC, NOT BaseModel) + multiple-inheritance subclasses ((BaseModel, MarkerABC)) + __get_pydantic_core_schema__ override = isinstance() works first-class AND Pydantic field-emit order is preserved AND TypeAdapter(MarkerABC) builds discriminated union of __subclasses__ on the fly. Wire-byte equivalent to Phase 4.7."
    - "Wave-aware ABC subclassing: concrete provider classes subclass LLMProvider(ABC) and add a build_agent stub raising NotImplementedError, deferring real impl to the next wave. The ABC contract is locked at the foundation; the body fills in incrementally."
    - "TYPE_CHECKING guard pattern for not-yet-installed third-party deps: ``from __future__ import annotations`` + ``if TYPE_CHECKING: from pydantic_ai import Agent`` keeps the module importable before Wave 4 install. Forward-ref strings resolve at type-check time only."

key-files:
  created:
    - backend/app/llm/base.py — LLMProvider(ABC) with 4 abstract methods (get_provider_name / validate_config / list_models / build_agent)
    - backend/app/chat/deps.py — ChatDeps(@dataclass(frozen=True)) — flight_client, session_id, user_id
    - backend/app/chat/store.py — ConversationStore(ABC) + InMemoryConversationStore with append/load/delete/list_for_user
    - .planning/phases/05-pydanticai-migration/deferred-items.md — three test files broken by protocol.py deletion (Wave 2/3 scope)
  modified:
    - backend/app/llm/__init__.py — re-export LLMProvider from app.llm.base; drop BoundProvider docstring references
    - backend/app/llm/factory.py — import LLMProvider from app.llm.base; drop reasoning_model_prefixes kwarg from OllamaProvider construction
    - backend/app/llm/providers/__init__.py — package docstring: "Phase 5 D-01..D-03 ABC subclass" framing
    - backend/app/llm/providers/ollama.py — explicit ``class OllamaProvider(LLMProvider):``; bind_tools annotation BoundProvider→Any; build_agent NotImplementedError stub
    - backend/app/llm/providers/openai.py — same pattern as ollama.py
    - backend/app/llm/providers/anthropic.py — same pattern as ollama.py
    - backend/app/llm/providers/lmstudio.py — same pattern as ollama.py
    - backend/app/chat/__init__.py — re-export ChatDeps, ConversationStore, InMemoryConversationStore
    - backend/app/chat/service.py — drop BoundProvider TYPE_CHECKING import; type _bound_providers as dict[str, Any]
    - backend/app/chat/models.py — replace Annotated alias with marker-ABC StreamEvent; multi-inherit subclasses on (BaseModel, StreamEvent)
    - backend/app/config.py — drop Settings.ollama_reasoning_model_prefixes; add Settings.openai_o_series_model_prefixes = ("o1", "o3")
    - backend/tests/conftest.py — re-route LLMProvider import to app.llm.base; drop BoundProvider spec
  deleted:
    - backend/app/llm/protocol.py — outright deletion per CONTEXT.md anti-pattern lock (no shim)

key-decisions:
  - "Marker ABC (pure abc.ABC, NOT BaseModel) for StreamEvent — PATTERNS.md target shape ``class StreamEvent(BaseModel, ABC)`` was empirically incompatible with the Phase 4.7 wire-byte golden file (Pydantic v2 emits inherited base fields BEFORE subclass fields, which would shift session_id from last → second position and break frontend SSE parsing). The plan's action paragraph anticipated this conflict ('adjust whichever ordering keeps test_stream_event_wire_compat green') — this commit takes the marker-ABC route."
  - "TYPE_CHECKING guard for pydantic_ai imports in app.llm.base and app.chat.store — pydantic_ai is installed in Wave 4 (Plan 05-06); using TYPE_CHECKING + ``from __future__ import annotations`` keeps the modules importable through Waves 1-3."
  - "Concrete providers subclass LLMProvider(ABC) explicitly with build_agent stubs (NotImplementedError) — closes test_protocol_abc.py's ``issubclass(OllamaProvider, LLMProvider)`` requirement in Wave 1. Wave 2 (Plan 05-03) replaces the stub bodies."
  - "Anti-pattern lock honoured rigorously: ``grep -rEn 'BoundProvider' backend/app`` returns zero matches, ``app/llm/protocol.py`` is deleted outright (no transitional shim), ``Settings.ollama_reasoning_model_prefixes`` removed in the same commit as the OllamaProvider kwarg drop (closes A2 mid-state breakage)."

patterns-established:
  - "Marker-ABC + multi-inheritance for Pydantic event hierarchies — abc.ABC stays pure (no BaseModel mixin), concrete subclasses inherit (BaseModel, ABC). Avoids Pydantic v2 field-order pitfalls when wire-byte preservation is required."
  - "Wave-staged ABC subclassing — foundation wave (this plan) makes concrete classes subclass the ABC + adds NotImplementedError stubs for not-yet-implemented abstract methods; subsequent waves replace the stubs. Keeps the ABC contract locked early without forcing all impls in the foundation wave."

requirements-completed: []  # REQ-pydantic-ai-migration and REQ-p5-stream-event-abc are advanced (not completed); SC-2 and SC-3 advance per success_criteria — full requirement satisfaction lands when ChatService and providers are rewritten in Waves 2-3.

# Metrics
duration: 14min
completed: 2026-06-03
---

# Phase 5 Plan 02: Wave 1 Foundations Summary

**LLMProvider Protocol→ABC, ChatDeps + ConversationStore foundations, and StreamEvent marker-ABC refactor with byte-equivalent SSE wire format — three task commits land the abstract surfaces every later wave depends on.**

## Performance

- **Duration:** ~14 min
- **Started:** 2026-06-03T05:14:44Z
- **Completed:** 2026-06-03T05:29:00Z
- **Tasks:** 3 (all auto, none paused at checkpoints)
- **Files created:** 4 (3 production modules + 1 deferred-items.md)
- **Files modified:** 13 production + 1 test conftest
- **Files deleted:** 1 (`backend/app/llm/protocol.py`)
- **Tests verified:** 27 passed, 3 skipped (skips are pydantic_ai-gated; Wave 4 lands the dep)

## Accomplishments

- **LLMProvider Protocol → ABC** (Task 1, commit `6d7b570`). The Phase 4.5 two-tier `LLMProvider` + `BoundProvider` Protocol pair collapses into a single `LLMProvider(ABC)` in `app/llm/base.py`. `app/llm/protocol.py` is deleted outright (CONTEXT.md anti-pattern lock — pure rename + retype, no shim). The four concrete provider classes explicitly subclass it via `class OllamaProvider(LLMProvider):` etc., with a `build_agent` `NotImplementedError` stub deferred to Wave 2 (Plan 05-03).
- **ChatDeps + ConversationStore foundations** (Task 2, commit `ba287f8`). `app/chat/deps.py` introduces `@dataclass(frozen=True) class ChatDeps` carrying `flight_client / session_id / user_id` (D-05). `app/chat/store.py` introduces `ConversationStore(ABC)` (`append/load/delete/list_for_user`) plus `InMemoryConversationStore` with immutable `existing + messages` concat semantics. `pydantic_ai.messages.ModelMessage` imports under TYPE_CHECKING so the module loads before Wave 4 lands the dep.
- **StreamEvent marker ABC + Settings o-series knob** (Task 3, commit `7aef8ae`). The Phase 4.7 `Annotated[..., Field(discriminator="type")]` alias retires; a real `class StreamEvent(ABC)` (pure abc.ABC, NOT BaseModel) takes its place. Five concrete subclasses inherit `(BaseModel, StreamEvent)` via multiple inheritance — `isinstance(event, StreamEvent)` checks first-class while Pydantic field-emit order stays canonical (`type, ..., session_id`). `StreamEvent.__get_pydantic_core_schema__` builds a discriminated union of `__subclasses__()` on `TypeAdapter` construction, preserving the Phase 4.7 round-trip semantics for `tests/utils/sse.py`'s `parse_sse_events`. `Settings.ollama_reasoning_model_prefixes` is removed (PydanticAI parses `<think>` tags natively per RESEARCH OQ-04); `Settings.openai_o_series_model_prefixes = ("o1", "o3")` is added for the D-14 dispatch knob (Wave 2 wires it).
- **Wave 0 RED tests turn GREEN — three test files** (subset; the full Wave 0 → GREEN sweep happens incrementally across Waves 1-4):
  * `tests/unit/llm/test_protocol_abc.py`: 7/7 passed (LLMProvider ABC conformance + 4 provider subclass checks + BoundProvider-removed regression lock).
  * `tests/unit/chat/test_deps.py`: 3/3 passed (frozen dataclass + field shape + type hints).
  * `tests/unit/chat/test_stream_event_abc.py`: 4/4 passed (ABCMeta marker + isinstance + TypeAdapter dispatch + not-Protocol).
  * `tests/unit/chat/test_stream_event_wire_compat.py`: 5/5 passed — **byte-equivalent SSE wire format preserved**.
  * `tests/unit/test_stream_events.py`: 8/8 passed — Phase 4.7 discriminator round-trip semantics intact (TypeAdapter dispatch via marker-ABC `__get_pydantic_core_schema__`).
- `tests/unit/chat/test_conversation_store.py`: SKIPPED at module level via `pytest.importorskip("pydantic_ai.messages")` — turns GREEN automatically once Wave 4 installs `pydantic-ai`.

## Task Commits

Each task committed atomically:

1. **Task 1: Rename protocol.py → base.py and convert LLMProvider Protocol → ABC; delete BoundProvider** — `6d7b570` (refactor)
2. **Task 2: Create ChatDeps and ConversationStore foundations** — `ba287f8` (feat)
3. **Task 3: Refactor StreamEvent to ABC + 5 subclasses; preserve wire format byte-for-byte; add Settings o-series knob** — `7aef8ae` (refactor)

## Files Created/Modified

### Created (production)

- `backend/app/llm/base.py` — `LLMProvider(ABC)` with four abstract methods (`get_provider_name`, `validate_config`, `list_models`, `build_agent`); `from pydantic_ai import Agent` under TYPE_CHECKING.
- `backend/app/chat/deps.py` — `@dataclass(frozen=True) class ChatDeps` (`flight_client: FlightAPIClient`, `session_id: str`, `user_id: str`).
- `backend/app/chat/store.py` — `ConversationStore(ABC)` + `InMemoryConversationStore`; immutable concat in `append`; defensive list copy in `load`; `pop(..., None)` in `delete`; Phase 5 `list_for_user → []` (D-09 keeps user-indexing on `ChatService._metadata`).

### Created (planning)

- `.planning/phases/05-pydanticai-migration/deferred-items.md` — tracks three out-of-scope test files broken by `app.llm.protocol` deletion (Wave 2/3 scope: `test_protocol_conformance.py`, `test_chat_service.py`, `test_chat_stream.py` via `tests/fixtures/llm.py`).

### Deleted

- `backend/app/llm/protocol.py` — outright deletion per CONTEXT.md anti-pattern lock ("Don't ship a `ProtocolProvider` adapter alongside the new ABC — pure rename + retype, no backwards-compat shim"). 92 lines (Protocol declarations) gone in one commit.

### Modified

- `backend/app/llm/__init__.py` — re-export `LLMProvider` from `app.llm.base`; remove `BoundProvider` references from docstring + `__all__`.
- `backend/app/llm/factory.py` — `from app.llm.base import LLMProvider`; drop `reasoning_model_prefixes=...` kwarg from `OllamaProvider(...)` (closes A2 mid-state breakage where `Settings` no longer carries the field).
- `backend/app/llm/providers/__init__.py` — package docstring rewrite ("Phase 5 D-01..D-03 ABC subclass" framing).
- `backend/app/llm/providers/{ollama,openai,anthropic,lmstudio}.py` — explicit `class XxxProvider(LLMProvider):` subclassing; `from app.llm.base import LLMProvider`; drop `BoundProvider` import; `bind_tools` return-type annotation `BoundProvider → Any`; add `build_agent` stub raising `NotImplementedError("...Wave 2 / Plan 05-03")`.
- `backend/app/chat/__init__.py` — re-export `ChatDeps`, `ConversationStore`, `InMemoryConversationStore` (alphabetical `__all__`).
- `backend/app/chat/service.py` — drop the `from app.llm.protocol import BoundProvider` TYPE_CHECKING import; type `_bound_providers: dict[str, Any]` with a Wave 3 follow-up comment.
- `backend/app/chat/models.py` — **lines 42–102 replaced** (alias + 5 subclasses → marker-ABC `StreamEvent` + 5 multi-inherit subclasses); add `from abc import ABC` + `import operator` + `from functools import reduce`; subclass declarations preserve the Phase 4.7 field order (`type, ..., session_id` last).
- `backend/app/config.py` — **lines 72–83 replaced** (`ollama_reasoning_model_prefixes` deletion + `openai_o_series_model_prefixes = ("o1", "o3")` insertion).
- `backend/tests/conftest.py` — re-route `LLMProvider` import to `app.llm.base`; drop `BoundProvider` import + spec from `mock_llm_factory` (now uses an unspec'd `MagicMock` for the bound runnable).

## Decisions Made

- **Marker ABC for `StreamEvent`** (NOT `class StreamEvent(BaseModel, ABC)` per PATTERNS.md target). Empirically verified that the BaseModel+ABC target shape shifts `session_id` from the last to the second-emitted field, breaking the Phase 4.7 wire-byte golden file. The plan's `<action>` paragraph for Task 3 explicitly authorised "adjust whichever ordering keeps Wave 0's `test_stream_event_wire_compat.py` green"; this commit takes that route. Multi-inheritance `(BaseModel, StreamEvent)` keeps Pydantic field-order natural while still satisfying `isinstance()`. `StreamEvent.__get_pydantic_core_schema__` overrides at the ABC level so `TypeAdapter(StreamEvent)` dispatches to a discriminated union of `__subclasses__()` — preserves `tests/utils/sse.py`'s `parse_sse_events` round-trip behaviour with no change at the call site.
- **TYPE_CHECKING guard for `pydantic_ai` imports** in `app/llm/base.py` and `app/chat/store.py`. The plan's `<interfaces>` block specifies `from pydantic_ai import Agent` (and `from pydantic_ai.messages import ModelMessage`) but `pydantic-ai` does not land in the lockfile until Wave 4 (Plan 05-06). Without `TYPE_CHECKING` guards, importing `app.llm.base` at runtime would `ModuleNotFoundError`, taking down `app.api.main` startup and the entire test suite. With the guard + `from __future__ import annotations`, the modules load cleanly and forward-ref annotations resolve at type-check time only. Documented in module docstrings.
- **Wave-staged provider subclassing**: concrete providers subclass `LLMProvider(ABC)` in this plan, but `build_agent` bodies stay as `NotImplementedError("...Wave 2 / Plan 05-03")` stubs. The ABC contract locks at the foundation; the bodies fill in incrementally.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 — Blocking] TYPE_CHECKING guard for `pydantic_ai` import in `app/llm/base.py`**
- **Found during:** Task 1 (LLMProvider ABC creation)
- **Issue:** The plan's `<interfaces>` block specifies `from pydantic_ai import Agent` as a top-level import on `app/llm/base.py`. `pydantic-ai` is not in the lockfile until Wave 4 (Plan 05-06). Top-level import would `ModuleNotFoundError` on every Python invocation, taking down `app.api.main` startup.
- **Fix:** `from __future__ import annotations` at the top of `app/llm/base.py`; `if TYPE_CHECKING: from pydantic_ai import Agent`. Forward-ref annotations are still typed correctly for mypy/pyright.
- **Files modified:** `backend/app/llm/base.py`
- **Verification:** `cd backend && uv run python -c "from app.llm.base import LLMProvider"` succeeds; the file imports cleanly without `pydantic_ai` installed.
- **Committed in:** `6d7b570` (Task 1)

**2. [Rule 3 — Blocking] TYPE_CHECKING guard for `pydantic_ai.messages` import in `app/chat/store.py`**
- **Found during:** Task 2 (ConversationStore ABC creation)
- **Issue:** Same as #1 — the store needs `ModelMessage` for type annotations on `append`/`load` signatures, but `pydantic_ai.messages` is not yet installed.
- **Fix:** Same pattern — `from __future__ import annotations` + `if TYPE_CHECKING: from pydantic_ai.messages import ModelMessage`.
- **Files modified:** `backend/app/chat/store.py`
- **Verification:** `cd backend && uv run python -c "from app.chat.store import ConversationStore, InMemoryConversationStore"` succeeds.
- **Committed in:** `ba287f8` (Task 2)

**3. [Rule 3 — Blocking] `tests/conftest.py` import refactor**
- **Found during:** Task 1 (post-`protocol.py` deletion)
- **Issue:** `backend/tests/conftest.py` imports `from app.llm.protocol import BoundProvider, LLMProvider`. Deleting `app/llm/protocol.py` would break ALL test collection (conftest is loaded by every pytest run), making the verify command fail spuriously.
- **Fix:** Re-route `LLMProvider` import to `app.llm.base`. Drop `BoundProvider` import. Change `mock_llm_factory`'s bound runnable from `MagicMock(spec=BoundProvider)` to an unspec'd `MagicMock()` (the second-tier Protocol retired in this plan; tests that need realistic `astream` shape attach their own mock per the existing convention).
- **Files modified:** `backend/tests/conftest.py`
- **Verification:** `cd backend && uv run pytest tests/unit/llm/test_protocol_abc.py -v` collects + runs cleanly (was previously failing with `ModuleNotFoundError: app.llm.protocol`).
- **Committed in:** `6d7b570` (Task 1)

**4. [Rule 3 — Blocking] `app/chat/service.py` `BoundProvider` annotation removal**
- **Found during:** Task 1 (the `grep -rEn "BoundProvider" backend/app` verify check)
- **Issue:** `app/chat/service.py` had a TYPE_CHECKING import `from app.llm.protocol import BoundProvider` and a runtime annotation `self._bound_providers: dict[str, BoundProvider] = {}`. Even though `from __future__ import annotations` makes the annotation a forward-ref string at runtime (so the import-error wouldn't crash on import), the verify check `grep -rEn "BoundProvider" backend/app` would still fail because the literal string is in the source.
- **Fix:** Drop the TYPE_CHECKING import; type the dict as `dict[str, Any]` with a comment pointing to Wave 3 / Plan 05-04 (which replaces the dict with `self._agents: dict[str, Agent]`).
- **Files modified:** `backend/app/chat/service.py`
- **Verification:** `grep -rEn "BoundProvider" backend/app` returns no results (exit 1). `cd backend && uv run python -c "from app.chat.service import ChatService"` succeeds.
- **Committed in:** `6d7b570` (Task 1)

**5. [Rule 1 — Bug] Marker-ABC for `StreamEvent` instead of `BaseModel + ABC`**
- **Found during:** Task 3 (StreamEvent refactor, before writing the new file)
- **Issue:** PATTERNS.md's target shape `class StreamEvent(BaseModel, ABC):` with `session_id: str` declared on the base class would shift the `session_id` field from LAST (Phase 4.7 wire layout) to SECOND in the JSON output, because Pydantic v2 emits inherited base fields BEFORE subclass fields. Wave 0's `test_stream_event_wire_compat.py` golden file would FAIL byte-equivalence against the Phase 4.7 reference (and this would silently break the frontend SSE parser).
- **Fix:** Use a pure `class StreamEvent(ABC):` (NOT `BaseModel`) and have the five concrete subclasses inherit `(BaseModel, StreamEvent)` via multiple inheritance. `session_id` stays declared on each subclass, preserving Phase 4.7 field order. `StreamEvent.__get_pydantic_core_schema__` overrides to build a discriminated union of `__subclasses__()` on `TypeAdapter` construction — preserves the existing `parse_sse_events` round-trip semantics. The plan's `<action>` paragraph anticipated this conflict ("adjust whichever ordering keeps Wave 0's `test_stream_event_wire_compat.py` green") so this is a sanctioned deviation.
- **Files modified:** `backend/app/chat/models.py`
- **Verification:** All 5 wire-compat golden tests pass byte-for-byte; all 4 ABC tests pass (`isinstance(StreamEvent, ABCMeta)`, subclass `isinstance`, `TypeAdapter` dispatch, not-Protocol); all 8 existing `test_stream_events.py` tests pass (TypeAdapter discriminator round-trip).
- **Committed in:** `7aef8ae` (Task 3)

**6. [Rule 2 — Missing Critical] `build_agent` `NotImplementedError` stubs on each provider**
- **Found during:** Task 1 (after making providers subclass `LLMProvider(ABC)`)
- **Issue:** `LLMProvider(ABC)` declares `build_agent` as `@abstractmethod`. Concrete providers that subclass it without implementing `build_agent` are not instantiable (Python raises `TypeError: Can't instantiate abstract class …`). `tests/unit/llm/test_protocol_abc.py` instantiates each provider (`OllamaProvider(model="qwen3:4b", ...)`) — without a `build_agent` method, the verify command would fail.
- **Fix:** Add `def build_agent(self, tools: Sequence[Any], deps_type: type[Any]) -> Any: raise NotImplementedError("...Wave 2 / Plan 05-03 implements this")` to each of the four provider classes. Wave 2 (Plan 05-03) replaces the bodies with the real PydanticAI `Agent` construction.
- **Files modified:** `backend/app/llm/providers/{ollama,openai,anthropic,lmstudio}.py`
- **Verification:** `tests/unit/llm/test_protocol_abc.py` passes 7/7 (including the 4 `issubclass(...)` + `isinstance(...)` instantiation checks).
- **Committed in:** `6d7b570` (Task 1)

---

**Total deviations:** 6 auto-fixed (4 blocking, 1 bug, 1 missing-critical)
**Impact on plan:** All six were necessary to satisfy the plan's own verify commands. The marker-ABC choice for `StreamEvent` (#5) is a sanctioned deviation per the plan's action paragraph; the four TYPE_CHECKING / annotation refactors (#1–#4) close mid-wave breakage that would otherwise prevent any module from importing; the `build_agent` stub (#6) is the canonical Wave-staged ABC subclassing pattern. No scope creep.

## Issues Encountered

- **Three pre-existing test files broken by `app.llm.protocol` deletion** — `test_protocol_conformance.py`, `test_chat_service.py`, `test_chat_stream.py` (via `tests/fixtures/llm.py`). These are out-of-scope for Plan 05-02 (verify only targets `test_protocol_abc.py` + the chat-package Wave 0 stubs). Documented in `.planning/phases/05-pydanticai-migration/deferred-items.md` with owners (Wave 2 / Wave 3) and disposition.

## User Setup Required

None — no external services, env vars, or dashboard config introduced by this plan. All changes are internal abstract-surface refactors.

## Confirmation: Wire-format byte-equivalence

The Phase 4.7 SSE golden bytes captured in Plan 05-01's `tests/unit/chat/test_stream_event_wire_compat.py` are byte-equivalent against the Wave 1 `StreamEvent` marker-ABC + multi-inherit subclass layout. All five `model_dump_json()` outputs match the pinned literals exactly:

```
ContentEvent(chunk="hi", session_id="s1") →
  {"type":"content","chunk":"hi","session_id":"s1"} ✓

ThinkingEvent(chunk="think", session_id="s1") →
  {"type":"thinking","chunk":"think","session_id":"s1"} ✓

ToolCallEvent(tool_name="search_flights", tool_args={"origin":"LAX"}, session_id="s1") →
  {"type":"tool_call","tool_name":"search_flights","tool_args":{"origin":"LAX"},"session_id":"s1"} ✓

ToolResultEvent(tool_name="search_flights", tool_result="ok", elapsed_ms=42, session_id="s1") →
  {"type":"tool_result","tool_name":"search_flights","tool_result":"ok","elapsed_ms":42,"session_id":"s1"} ✓

ErrorEvent(error_code=ErrorCode.tool_error, message="boom", retryable=True,
           tool_name="search_flights", raw_detail="scrubbed", session_id="s1") →
  {"type":"error","error_code":"tool_error","message":"boom","retryable":true,
   "tool_name":"search_flights","raw_detail":"scrubbed","session_id":"s1"} ✓
```

Frontend SSE parser unaffected.

## Confirmation: `app/llm/protocol.py` deletion

```bash
$ test ! -f backend/app/llm/protocol.py && echo "OK: protocol.py deleted"
OK: protocol.py deleted

$ git diff --diff-filter=D --name-only ba287f8^ 6d7b570
backend/app/llm/protocol.py
```

The four concrete providers now import `LLMProvider` from `app.llm.base`:

```bash
$ grep -l "from app.llm.base import LLMProvider" backend/app/llm/providers/*.py
backend/app/llm/providers/anthropic.py
backend/app/llm/providers/lmstudio.py
backend/app/llm/providers/ollama.py
backend/app/llm/providers/openai.py
```

## Self-Check: PASSED

Files claimed to exist:
- `backend/app/llm/base.py` — FOUND
- `backend/app/chat/deps.py` — FOUND
- `backend/app/chat/store.py` — FOUND
- `.planning/phases/05-pydanticai-migration/deferred-items.md` — FOUND
- `backend/app/llm/protocol.py` — confirmed DELETED (`test ! -f` exit 0)

Commit hashes claimed:
- `6d7b570` (Task 1) — FOUND in git log
- `ba287f8` (Task 2) — FOUND in git log
- `7aef8ae` (Task 3) — FOUND in git log

Test verification:
- 27 tests passed across `test_protocol_abc.py` (7), `test_deps.py` (3), `test_stream_event_abc.py` (4), `test_stream_event_wire_compat.py` (5), `test_stream_events.py` (8); 3 skipped (pydantic_ai-gated, expected per Wave 0 design).

## Next Phase Readiness

- **Wave 2 / Plan 05-03 (Providers Rewrite)** can now run: `LLMProvider(ABC)` is locked at `app.llm.base.LLMProvider`. Each provider already explicitly subclasses it; Wave 2's job is to replace the `bind_tools` LangChain bodies + `build_agent` `NotImplementedError` stubs with real PydanticAI `Agent` construction (plus thread `Settings.openai_o_series_model_prefixes` into the OpenAI dispatcher).
- **Wave 3 / Plan 05-04 (ChatService Rewrite)** has its dependencies in place: `ChatDeps` + `ConversationStore` + `InMemoryConversationStore` + the `StreamEvent` marker ABC are all importable today. Wave 3 swaps `self._bound_providers: dict[str, Any]` → `self._agents: dict[str, Agent]` and `self._histories: dict[str, InMemoryChatMessageHistory]` → `self._store: ConversationStore`.
- **Wave 4 / Plan 05-06 (Dep Swap)** still owns the `pydantic-ai>=0.8.1` install + `langchain*`/`langgraph` removal. Until then, the TYPE_CHECKING guards in `app.llm.base` and `app.chat.store` keep the modules importable.
- **Three deferred test files** (`test_protocol_conformance.py`, `test_chat_service.py`, `test_chat_stream.py` via `tests/fixtures/llm.py`) need attention in Wave 2/3. Tracked in `deferred-items.md`.

---

*Phase: 05-pydanticai-migration*
*Plan: 02*
*Completed: 2026-06-03*
