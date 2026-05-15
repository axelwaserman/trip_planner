# Decisions (extracted ADRs)

> Synthesizer note: Decisions below were extracted from `ARCHITECTURE.md` per orchestrator instruction. The parent doc was classified `DOC`, but it embeds 5 explicit ADR sections (`ADR-001` through `ADR-005`) with `Status` fields. Accepted ADRs are treated as **locked decisions**; the Withdrawn ADR is recorded for history.

---

## ADR-001: LangChain 1.0 with bind_tools() Pattern

- source: `/Users/axel/code/trip_planner/ARCHITECTURE.md` (lines 319–340)
- status: **Accepted** → **locked**
- date: 2025-11-10
- scope: agent framework, tool calling

**Context:** Need agent framework for tool calling with LLMs.

**Decision:** Use LangChain 1.0 `bind_tools()` pattern instead of older `create_agent()` approach.

**Rationale:**
- LangChain 1.0 uses LangGraph under the hood (more flexible)
- `bind_tools()` works with any chat model that supports function calling
- Simpler pattern: just bind tools to LLM, no separate agent object
- Easier to test (mock LLM directly)

**Consequences:**
- Cleaner code, less abstraction
- Works with streaming out of the box
- Easy to switch LLM providers
- Less guidance on agent patterns (more DIY)

---

## ADR-002: Global Chat Store

- source: `/Users/axel/code/trip_planner/ARCHITECTURE.md` (lines 343–365)
- status: **Withdrawn / never implemented**
- date: 2025-11-08 (proposal); withdrawn 2025-11-14
- scope: conversation history persistence

**Context:** Need to maintain conversation history across requests.

**Proposal (never shipped):** Use a global `_global_chat_store` dictionary with session IDs.

**Why withdrawn:** The proposal never reached the codebase. `NOW.md` (2025-11-14) records: "No global `_global_chat_store` exists - was a misunderstanding." `CLAUDE.md` confirms: "There is no global store." The actual implementation uses `ChatService._histories` dict managed per-instance — no global store was ever introduced.

**Why preserved:** historical record of a proposed-but-never-implemented pattern; downstream consumers should NOT treat this as an active constraint and should NOT assume the deprecated pattern was ever live.

---

## ADR-003: Streaming with Server-Sent Events

- source: `/Users/axel/code/trip_planner/ARCHITECTURE.md` (lines 368–390); implementation at `/Users/axel/code/trip_planner/backend/app/api/routes/routes.py` (lines 6, 26, 31, 42, 76)
- status: **locked-as-implemented** (differs from ARCHITECTURE.md target)
- date: 2025-11-09
- scope: real-time LLM response streaming to frontend

**Context:** Need real-time streaming of LLM responses to frontend.

**Decision (as implemented):** Use Server-Sent Events (SSE) with FastAPI's built-in `StreamingResponse` from `fastapi.responses`.

**Note on drift from ARCHITECTURE.md:** The original ARCHITECTURE.md target named `EventSourceResponse` from `sse_starlette`. That dependency never landed; the codebase ships `StreamingResponse` instead. The locked outcome is the implemented form (`StreamingResponse`), not the documented target. Verification: `grep -n "EventSourceResponse\|StreamingResponse\|sse_starlette" backend/app/api/routes/routes.py` returns only `StreamingResponse`; `sse_starlette` is not a dependency.

**Rationale:**
- Native browser support (EventSource API)
- Simpler than WebSockets for unidirectional streaming
- Works with HTTP/1.1 (no HTTP/2 required)
- `StreamingResponse` is built into FastAPI — no extra dependency required

**Consequences:**
- No additional libraries needed
- Simple client implementation
- Unidirectional only (no client→server streaming)
- Limited to text data (JSON encoded)
- Auto-reconnect semantics depend on the client's `EventSource` implementation, since `StreamingResponse` does not add server-side reconnect features that `sse_starlette` would provide

---

## ADR-004: Pydantic Models for All Data Structures

- source: `/Users/axel/code/trip_planner/ARCHITECTURE.md` (lines 393–414)
- status: **Accepted** → **locked**
- date: 2025-11-06
- scope: data validation, serialization, type safety across the application

**Context:** Need data validation and serialization throughout the app.

**Decision:** Use Pydantic models for all data structures (no raw dicts).

**Rationale:**
- Built-in validation with clear error messages
- Automatic OpenAPI schema generation
- Type safety with mypy integration
- Serialization/deserialization for free

**Consequences:**
- Fewer bugs from invalid data
- Better IDE autocomplete
- Self-documenting API
- Slight performance overhead (negligible)

---

## ADR-005: Mock-First External API Integration

- source: `/Users/axel/code/trip_planner/ARCHITECTURE.md` (lines 417–438)
- status: **Accepted** → **locked**
- date: 2025-11-10
- scope: flight search client implementation strategy

**Context:** Need flight search functionality but don't want to depend on external API during development.

**Decision:** Build mock client first, real API later (Phase 5).

**Rationale:**
- Faster development (no API credentials needed)
- Reliable tests (no network flakiness)
- Abstract Client Pattern enables easy swap
- Can develop/test offline

**Consequences:**
- Fast iteration
- Deterministic tests
- No API costs during development
- Need to ensure mock matches real API behavior

---

## Implicit decisions (referenced by multiple docs, not formal ADRs)

The following design choices are stated in `CLAUDE.md` and `ARCHITECTURE.md` as project rules. They are not formal ADRs but appear consistently across docs and behave as locked technical constraints:

- **JWT auth via `pyjwt` + `pwdlib[argon2]`** for password hashing — source: `CLAUDE.md`, `IMPLEMENTATION_PLAN.md` Phase 1
- **mypy strict mode** — no bare `type: ignore` without explanatory comment — source: `CLAUDE.md`
- **All I/O `async def`** — no `requests`, no sync file I/O on async paths — source: `CLAUDE.md`
- **`uv` exclusively for Python package management** — never `pip`, `poetry`, `conda` — source: `CLAUDE.md`
- **`ruff` line length 100; `isort` first-party prefix `app`** — source: `CLAUDE.md`
- **Lifespan-managed singletons via `app.state`; no `@lru_cache`** — source: `ARCHITECTURE.md` (Dependency Injection Pattern), `pre-phase-4-refactor.md` Task 9
- **Tests live in `backend/tests/{unit,integration,e2e}` with markers; default test run excludes `slow`** — source: `CLAUDE.md`, `ARCHITECTURE.md`

These should be promoted to formal ADRs by the roadmapper if they merit decision-record status; otherwise they remain in `constraints.md`.
