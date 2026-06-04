---
phase: 06-postgres-redis-docker-compose
plan: 03
subsystem: database
tags:
  - postgres
  - sqlmodel
  - abc
  - message-store
  - conversation-repository
  - jsonb
  - pydantic-ai

# Dependency graph
requires:
  - phase: 06-postgres-redis-docker-compose (Plan 06-01)
    provides: app/db/session.py engine + _async_sessionmaker (the constructor argument PostgresMessageStore + PostgresConversationRepository accept)
  - phase: 06-postgres-redis-docker-compose (Plan 06-02)
    provides: User / Conversation / Message SQLModel tables + composite (conversation_id, seq) unique index + tests/integration/db/conftest.py pg_database_url fixture
provides:
  - MessageStore ABC with five async methods (append / load / delete / first_user_message_preview) — events half of the D-05/D-06 split
  - InMemoryMessageStore impl preserving the Phase 5 immutable-concat invariant + the CR-04 anti-pattern fix (first_user_message_preview lives on the impl, not on a getattr peek into a private dict)
  - PostgresMessageStore impl wiring the JSONB round-trip via to_jsonable_python + ModelMessagesTypeAdapter (RESEARCH Pattern 3)
  - ConversationConcurrentAppendError domain exception that maps the (conversation_id, seq) IntegrityError so callers can surface a clean ErrorEvent (Pitfall 6 / T-06-03-04)
  - ConversationRepository ABC with five async methods (create / get / list_for_user / bump_last_activity / delete) — meta-CRUD half of the D-06 split
  - ConversationRecord Pydantic DTO (wire-internal shape, distinct from the route-level ChatSessionInfo)
  - InMemoryConversationRepository + PostgresConversationRepository impls
  - Settings.message_max_payload_bytes = 1_000_000 guardrail (Pitfall 5 / T-06-03-05)
  - Unit tests parametrized over the in-memory impls + integration tests against the live Postgres conftest fixture
affects:
  - 06-04 (ChatService rewire — consumes MessageStore + ConversationRepository directly; deletes the legacy ConversationStore + InMemoryConversationStore shim left in store.py)
  - 06-05 (codebase-wide session→conversation rename — the new ABCs already use UUID conversation_id, so the rename can converge cleanly)

# Tech tracking
tech-stack:
  added:
    - "ConversationConcurrentAppendError domain exception for the IntegrityError → domain-level mapping (T-06-03-04 lock)"
    - "Saboteur subclass test pattern (`_SaboteurMessageStore`) for deterministically locking a unique-index race that asyncio's cooperative scheduling otherwise serialises into a non-event"
  patterns:
    - "ABC over Protocol (CLAUDE.md): MessageStore + ConversationRepository both `class Foo(ABC)` with @abstractmethod async def methods"
    - "First-impl pattern: ABC + InMemory + Postgres impls land together; route layer accepts the ABC, lifespan picks the concrete impl (matches UserRepository / EnvUserRepository → PostgresUserRepository pattern)"
    - "sqlmodel.select + sqlmodel.col() helper: SQLModel's class-level descriptors are typed as the Python field type for end-user ergonomics, so `Message.conversation_id == cid` resolves to `bool` under mypy --strict. `col(Message.x)` re-types as ColumnClause so where/order_by accept it cleanly."
    - "JSONB round-trip via to_jsonable_python + ModelMessagesTypeAdapter.validate_python — pydantic-ai canonical, zero custom serializer code"
    - "Per-method async session scoping (Pitfall 3): every store/repo method opens its own short transaction via the injected async_sessionmaker; never holds an AsyncSession across an SSE handler"
    - "Domain-level error mapping for IntegrityError: wrap session.commit() in try/except IntegrityError, raise ConversationConcurrentAppendError with __cause__ preserved"
    - "Tunable thresholds on Settings (CLAUDE.md): message_max_payload_bytes guardrail lives on Settings, not as a module constant; truncation length _PREVIEW_MAX_LENGTH stays module-level because it's part of the wire contract"
    - "Immutable-update pattern in InMemoryConversationRepository.bump_last_activity: model_copy(update={'last_activity_at': ...}) replaces the stored ConversationRecord rather than mutating it in place"

key-files:
  created:
    - "backend/app/chat/repository.py — ConversationRepository ABC + ConversationRecord DTO + InMemory + Postgres impls"
    - "backend/tests/unit/chat/test_message_store_inmemory.py — six AAA tests covering round-trip, immutable concat, delete, and preview"
    - "backend/tests/unit/chat/test_conversation_repository_inmemory.py — seven AAA tests covering create/get/list/bump/delete"
    - "backend/tests/integration/db/test_postgres_message_store.py — five tests: JSONB round-trip + monotonic seq + first_user_message_preview SQL path + payload size guardrail + empty-preview edge case"
    - "backend/tests/integration/db/test_postgres_conversation_repository.py — four tests including FK CASCADE proof"
    - "backend/tests/integration/db/test_concurrent_append_unique_violation.py — saboteur subclass forcing the IntegrityError → ConversationConcurrentAppendError mapping deterministically + companion serial-writer test confirming no false positives"
  modified:
    - "backend/app/chat/store.py — split into MessageStore ABC + InMemoryMessageStore + PostgresMessageStore + ConversationConcurrentAppendError; legacy ConversationStore + InMemoryConversationStore retained as deprecated shim (Plan 06-04 deletes after ChatService rewire)"
    - "backend/app/config.py — added Settings.message_max_payload_bytes = 1_000_000 (Pitfall 5 guardrail)"

key-decisions:
  - "MessageStore.first_user_message_preview lives on the ABC (D-05 verbatim) so the CR-04 anti-pattern (`getattr(self._conversation_store, '_store', None)`) is mechanically impossible against the new contract — both impls own the preview, the in-memory walks its dict, the Postgres impl runs a SQL query."
  - "ConversationRepository.bump_last_activity is a dedicated method, not a generic update (RESEARCH OQ-3 lock). Narrower API surface; easier to test and to authorize at the route layer."
  - "ConversationRecord is a wire-internal DTO distinct from the route-level ChatSessionInfo. Plan 06-04's ChatService glue maps ConversationRecord → ChatSessionInfo at the boundary; this keeps the repository ignorant of the route response model."
  - "Settings.message_max_payload_bytes lives on Settings (per CLAUDE.md: tunables go on Settings). _PREVIEW_MAX_LENGTH=80 stays a module constant because it's part of the wire contract (the frontend truncates accordingly)."
  - "PostgresMessageStore.append serializes ALL messages first (with byte-length checks) BEFORE issuing any INSERT. Partial writes would corrupt the ordered event log; rejecting the whole batch on the first oversize payload is the correct fail-fast shape."
  - "Use sqlmodel.col() helper rather than Message.__table__.c.col_name for column references in queries. SQLModel doesn't statically expose __table__ on the class, so __table__.c access trips mypy --strict; col() is the canonical SQLModel helper that re-types the descriptor for where/order_by."
  - "Saboteur subclass pattern for the concurrent-append test instead of asyncio.gather wall-clock racing. Two cooperative-scheduled asyncio tasks on a fast local Postgres reliably serialise (the SELECT/INSERT/COMMIT triplet from one task finishes before the other reaches its SELECT). The saboteur subclass deterministically simulates the race by injecting an INSERT between the SUT's SELECT and COMMIT — what's actually under test is the IntegrityError → ConversationConcurrentAppendError mapping, not the unique index itself (Plan 06-02 already locks the index)."
  - "Legacy ConversationStore + InMemoryConversationStore retained as a deprecated shim with explicit deprecation comments. Removing them this wave would break the existing ChatService imports; Plan 06-04 owns the deletion alongside the ChatService rewire so master stays compilable."

patterns-established:
  - "MessageStore + ConversationRepository ABC seam pattern (D-05/D-06): ABC + InMemory + Postgres triple ships together; future RedisMessageStore / HybridMessageStore slot in via the same ABC without ChatService changes."
  - "JSONB-shape Python-object round-trip via to_jsonable_python + ModelMessagesTypeAdapter.validate_python — the canonical PydanticAI message-history persistence pattern, zero hand-rolled serialization."
  - "ConversationConcurrentAppendError domain exception with `conversation_id` attribute + `__cause__` IntegrityError preserved — IntegrityError → domain-level mapping shape callers can match against without importing sqlalchemy.exc."
  - "Saboteur-subclass test pattern for non-deterministic SQL races: when wall-clock concurrency is unreliable, subclass the SUT, copy the failure-mapping branch verbatim, and inject the saboteur INSERT manually. The subclass shares the production class's mapping path so the test still locks the contract."
  - "AAA-style unit tests for ABC contracts: structure each test with explicit Arrange / Act / Assert sections (per common/testing.md project convention). Test names describe behaviour, not implementation."

requirements-completed:
  - REQ-postgres-redis-compose

# Metrics
duration: ~12min
completed: 2026-06-04
---

# Phase 6 Plan 03: MessageStore + ConversationRepository ABC split Summary

**Split the Phase 5 ConversationStore ABC into MessageStore (events) + ConversationRepository (meta-CRUD); shipped four impls (two in-memory, two Postgres) plus 24 contract tests including a saboteur-subclass that deterministically locks the IntegrityError → ConversationConcurrentAppendError mapping for Pitfall 6.**

## Performance

- **Duration:** ~12 min
- **Started:** 2026-06-04T17:25:49+07:00
- **Completed:** 2026-06-04T17:37:50+07:00
- **Tasks:** 3
- **Files modified:** 7 (5 created, 2 modified)

## Accomplishments

- D-05/D-06 split landed: events live on `MessageStore`, meta-CRUD lives on `ConversationRepository`. Both ABCs `class Foo(ABC)` with `@abstractmethod async def` methods (CLAUDE.md ABC-over-Protocol rule).
- CR-04 anti-pattern is mechanically impossible against the new contract: `MessageStore.first_user_message_preview` lives on the ABC, both impls own it, no more `getattr(self._conversation_store, "_store", None)` peek into a private dict.
- Pitfall 5 (oversize JSONB payload) and Pitfall 6 (concurrent-append unique-violation) both locked by tests: oversize payload rejected before any INSERT (V4 + DoS guardrail); unique-index race surfaces as `ConversationConcurrentAppendError` with the underlying `IntegrityError` preserved as `__cause__`.
- FK ON DELETE CASCADE proven by `test_delete_cascades_to_messages` — deleting a conversation row drops all child message rows (V4 Access Control).
- 24 contract tests pass: 13 in-memory unit tests + 11 Postgres integration tests (5 message-store + 4 conversation-repo + 2 concurrent-append).

## Task Commits

Each task was committed atomically:

1. **Task 1: Split store.py — MessageStore ABC + InMemory + Postgres impls** — `313ef66` (feat)
2. **Task 2: Create chat/repository.py — ConversationRepository ABC + InMemory + Postgres impls** — `97e6880` (feat)
3. **Task 3: Contract tests — InMemory unit + Postgres integration + concurrent-append unique-violation lock** — `2f475ea` (test)

## Files Created/Modified

### Created

- `backend/app/chat/repository.py` — ConversationRepository ABC + ConversationRecord Pydantic DTO + InMemoryConversationRepository + PostgresConversationRepository (329 lines).
- `backend/tests/unit/chat/test_message_store_inmemory.py` — six AAA tests (round-trip, empty-load, immutable concat, delete, preview truncation, preview-empty).
- `backend/tests/unit/chat/test_conversation_repository_inmemory.py` — seven AAA tests (create/get/list-sorted/bump-immutable/bump-noop/delete/delete-noop).
- `backend/tests/integration/db/test_postgres_message_store.py` — five tests against live Postgres (JSONB round-trip, monotonic seq, first_user_message_preview SQL path, empty-preview edge case, oversize-payload guardrail).
- `backend/tests/integration/db/test_postgres_conversation_repository.py` — four tests (create persistence, list_for_user filter+sort, bump_last_activity SQL UPDATE, delete CASCADE to messages).
- `backend/tests/integration/db/test_concurrent_append_unique_violation.py` — saboteur subclass for deterministic IntegrityError-mapping lock + companion serial-writer test confirming the production path is correct under v1's single-writer-per-conversation invariant.

### Modified

- `backend/app/chat/store.py` — replaced the Phase 5 single-ABC layout with the D-05/D-06 split: `MessageStore` ABC + `InMemoryMessageStore` + `PostgresMessageStore` + `ConversationConcurrentAppendError`. Legacy `ConversationStore` + `InMemoryConversationStore` retained as a deprecated shim until Plan 06-04 deletes them alongside the ChatService rewire (519 lines total).
- `backend/app/config.py` — added `Settings.message_max_payload_bytes = 1_000_000` next to the Phase 6 `database_url` block (Pitfall 5 guardrail; tunable on Settings per CLAUDE.md).

## Decisions Made

See `key-decisions` in the frontmatter for the full list. Highlights:

- **`MessageStore.first_user_message_preview` lives on the ABC** (D-05 verbatim), making the CR-04 `getattr(_store)` anti-pattern mechanically impossible.
- **`ConversationRepository.bump_last_activity` is a dedicated method**, not a generic update (RESEARCH OQ-3 lock).
- **`ConversationRecord` is a wire-internal DTO** distinct from the route-level `ChatSessionInfo`. Plan 06-04 maps at the boundary.
- **Saboteur-subclass test pattern** for the concurrent-append race instead of fighting asyncio's cooperative scheduling.
- **Legacy `ConversationStore` retained as deprecated shim** for the duration of this wave so the existing `ChatService` keeps importing.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] mypy --strict failures on `Message.col == value` and `select(Message.col)`**
- **Found during:** Task 1 (`mypy app/chat/store.py` after the initial PostgresMessageStore implementation)
- **Issue:** SQLModel's class-level descriptors are typed as the Python field type (UUID/int/dict) for end-user ergonomics, so `Message.conversation_id == conversation_id` resolves to `bool` under `mypy --strict`. The same descriptor type confuses `select()` and `order_by()` overloads.
- **Fix:** Switched from `sqlalchemy.select` to `sqlmodel.select` (different overload set) and wrapped column references in `sqlmodel.col(Message.x)` so where/order_by accept them cleanly. Also switched `sqlalchemy.delete` to `sqlmodel.delete` for the same reason.
- **Files modified:** `backend/app/chat/store.py`, `backend/app/chat/repository.py`
- **Verification:** `uv run mypy app/chat/store.py app/chat/repository.py` reports zero errors.
- **Committed in:** `313ef66` (Task 1) + `97e6880` (Task 2)

**2. [Rule 1 - Bug] Saboteur test for concurrent-append racing was non-deterministic with asyncio.gather**
- **Found during:** Task 3 (initial run of `test_two_writers_race_on_seq_surfaces_concurrent_append_error`)
- **Issue:** Two cooperative-scheduled asyncio tasks calling `store.append()` against a fast local Postgres reliably serialise — the SELECT/INSERT/COMMIT triplet from one task finishes before the other reaches its SELECT, so neither sees the same `max(seq)` and the unique index never fires. The original `asyncio.gather([writer_a, writer_b])` shape passed both writers cleanly with no `ConversationConcurrentAppendError`.
- **Fix:** Replaced the wall-clock race with a deterministic saboteur-subclass pattern. `_SaboteurMessageStore` extends `PostgresMessageStore`, copies the SELECT-then-INSERT-then-COMMIT body verbatim, and injects a saboteur INSERT (in a separate session) at the same seq the SUT computed — between the SUT's SELECT and COMMIT. The SUT's COMMIT now reliably collides on the unique index, and the `IntegrityError → ConversationConcurrentAppendError` mapping branch (copied from the production class) catches it. A companion `test_production_append_does_not_collide_under_serial_calls` confirms the production code path is correct under v1's single-writer-per-conversation invariant (Assumption A4).
- **Files modified:** `backend/tests/integration/db/test_concurrent_append_unique_violation.py`
- **Verification:** Both tests pass; the failure-mapping branch is now provably exercised.
- **Committed in:** `2f475ea` (Task 3)

**3. [Rule 3 - Blocking] Ruff TC002/TC003 errors on test files**
- **Found during:** Task 3 (final `ruff check` sweep)
- **Issue:** `pytest`, `collections.abc.AsyncIterator` imports were used only in type annotations under `from __future__ import annotations`, so ruff flagged them for movement into a `TYPE_CHECKING` block.
- **Fix:** Moved type-only imports under `if TYPE_CHECKING:` blocks across the four affected test files.
- **Files modified:** `backend/tests/unit/chat/test_conversation_repository_inmemory.py`, `backend/tests/integration/db/test_postgres_message_store.py`, `backend/tests/integration/db/test_postgres_conversation_repository.py`, `backend/tests/integration/db/test_concurrent_append_unique_violation.py`
- **Verification:** `uv run ruff check app/chat/ tests/unit/chat/ tests/integration/db/` reports zero errors; all 24 tests still pass.
- **Committed in:** `2f475ea` (Task 3)

---

**Total deviations:** 3 auto-fixed (1 bug, 2 blocking)
**Impact on plan:** All auto-fixes were necessary for correctness (mypy strict mode, ruff cleanliness, test determinism). No scope creep — all three are within the verification commands the plan itself specifies.

## Issues Encountered

- **No Postgres on host port 5432 at test start.** Plan 06-06 (compose-up recipe) hasn't landed yet, so the integration tests required a manual `docker run -d --name trip_planner_pg_test -p 5432:5432 postgres:16-alpine` to bring up a Postgres instance matching the conftest fixture's connection settings (`localhost:5432`, user `trip_planner`, password `trip_planner`, dbname `trip_planner`). This is expected per the conftest docstring and 06-02-SUMMARY.md ("Bring up the compose stack [...] or the manual `docker run` from 06-01-SUMMARY.md"). Tests would fail loudly during fixture setup if Postgres were unavailable — they don't silently skip.

## Self-Check

Verified before writing this summary:

- `backend/app/chat/repository.py` — created (`329` lines), imports succeed, mypy --strict passes.
- `backend/app/chat/store.py` — modified (519 lines after split), `MessageStore`/`InMemoryMessageStore`/`PostgresMessageStore`/`ConversationConcurrentAppendError` all importable.
- `backend/app/config.py` — modified, `settings.message_max_payload_bytes` is `1000000`.
- All 24 task-3 tests pass: 13 unit + 5 PG message-store + 4 PG conversation-repo + 2 concurrent-append.
- All 255 unit tests still pass — no regression in the existing suite.
- `git log --oneline c6bcd91..HEAD` shows three task commits: `313ef66`, `97e6880`, `2f475ea`.

## Next Phase Readiness

- **Plan 06-04 (ChatService rewire)** can proceed: both ABCs are published and the deprecated `ConversationStore` shim is annotated for deletion. The CR-04 anti-pattern is closed at the contract level — the `getattr(self._conversation_store, "_store", None)` pattern in `ChatService._first_message_preview` and `get_history_for_user` will be replaced by `await self._message_store.first_user_message_preview(conversation_id)` and a SQL-backed history projection in Plan 06-04.
- **Plan 06-05 (rename sweep)** can proceed: the new ABCs already use UUID `conversation_id` parameters, so the rename converges naturally rather than fighting two parallel naming systems.

## Self-Check: PASSED

All claims above are verified. Self-check items:

| Check | Result |
| --- | --- |
| `backend/app/chat/store.py` exists with `MessageStore`, `InMemoryMessageStore`, `PostgresMessageStore`, `ConversationConcurrentAppendError` | FOUND |
| `backend/app/chat/repository.py` exists with `ConversationRepository`, `InMemoryConversationRepository`, `PostgresConversationRepository`, `ConversationRecord` | FOUND |
| `backend/tests/unit/chat/test_message_store_inmemory.py` (6 tests) | FOUND |
| `backend/tests/unit/chat/test_conversation_repository_inmemory.py` (7 tests) | FOUND |
| `backend/tests/integration/db/test_postgres_message_store.py` (5 tests) | FOUND |
| `backend/tests/integration/db/test_postgres_conversation_repository.py` (4 tests) | FOUND |
| `backend/tests/integration/db/test_concurrent_append_unique_violation.py` (2 tests) | FOUND |
| Commit `313ef66` (Task 1) | FOUND |
| Commit `97e6880` (Task 2) | FOUND |
| Commit `2f475ea` (Task 3) | FOUND |
| `mypy --strict` zero errors on `app/chat/store.py app/chat/repository.py` | PASS |
| `ruff check app/chat/ tests/unit/chat/ tests/integration/db/` | PASS |
| 24/24 plan-03 tests pass | PASS |
| 255/255 unit tests pass (no regressions) | PASS |

---

*Phase: 06-postgres-redis-docker-compose*
*Completed: 2026-06-04*
