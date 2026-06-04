# ADR-006: Postgres + SQLModel + alembic Persistence Stack

**Date**: 2026-06-04
**Status**: Locked

<!-- Plain-text mirror for grep-based verification (exact match for ^Status: Locked$): -->
Status: Locked


## Context

Phase 6 re-platforms persistence from in-process dicts to Postgres. The
Phase 5 surface (PydanticAI `list[ModelMessage]`, `ConversationStore` ABC,
`UserRepository` ABC) needs a durable backing store before Phase 7 layers
on agent state, and downstream waves of Phase 6 (schema + alembic, stores,
routes + rename, seed flow) all assume the async DB stack already works.

Three constraints drive the choice:

1. **Async-only I/O** (CLAUDE.md). Every store / repository method is
   `async def`; SQLAlchemy must be used through `AsyncSession`, never the
   sync `Session`. The streaming SSE handler in `ChatService.chat_stream()`
   means session lifecycles must be carefully bounded — a session held open
   across an entire SSE stream wedges the connection pool (Pitfall 3).
2. **PydanticAI message round-trip stability** (Phase 5 OQ-05). Phase 5
   verified that `to_jsonable_python(result.all_messages())` →
   `ModelMessagesTypeAdapter.validate_python(rows)` round-trips cleanly.
   The chosen ORM must therefore support a JSONB column for the
   `Message.payload` shape locked in D-02 (event-log schema).
3. **`uv`-only package management, modern Python typing**. The stack must
   resolve cleanly through `uv lock`, support `mypy --strict`, and avoid
   the older `psycopg2` + sync `Session` patterns documented as deprecated
   in 06-RESEARCH.md.

D-01 (CONTEXT.md) explicitly required a Wave 0 spike to verify
`postgresql+psycopg://` async + SQLModel + SQLAlchemy 2.0 work end-to-end
against the ChatService event-log shape **before** the schema and stores
land. A failing spike would have forced a fallback to `asyncpg` and
reshaped Plans 06-02 through 06-06.

Phase 6 also chose to defer Redis (D-04). The ABC seams in D-05 and D-06
(`MessageStore` and `ConversationRepository`) keep the door open for a
future `RedisMessageStore` / `HybridMessageStore` without rewriting
`ChatService`.

## Decision

Use the following persistence stack as the locked Phase 6 default:

**Driver + ORM:**
- Driver: `psycopg[binary,pool]>=3.3.4`, async via the `postgresql+psycopg://`
  URL scheme. The `[binary]` extra ships precompiled libpq; the `[pool]`
  extra ships psycopg's native connection pool.
- ORM: `sqlmodel>=0.0.38` (which transitively pins `sqlalchemy>=2.0.50`).
  Async sessions use SQLModel's subclass at
  `sqlmodel.ext.asyncio.session.AsyncSession` — NOT SQLAlchemy's plain
  `AsyncSession` — so the rest of the codebase can keep `.exec()`
  ergonomics.
- Migrations: `alembic>=1.18.4`, configured at `backend/alembic.ini` with
  migrations under `backend/migrations/`. `env.py` reads
  `Settings.database_url` and imports SQLModel metadata for
  `--autogenerate`. Migrations execute on the host via `uv run alembic`;
  compose runs only the DB container (D-11).

The `app/db/session.py` factory exports three module-level objects:

```python
engine = create_async_engine(
    settings.database_url,
    pool_size=settings.db_pool_size,
    max_overflow=settings.db_pool_overflow,
    echo=settings.debug,
)

_async_sessionmaker: async_sessionmaker[AsyncSession] = async_sessionmaker(
    engine,
    class_=AsyncSession,            # SQLModel's subclass
    expire_on_commit=False,         # Pitfall 8 lock
)

async def get_session() -> AsyncGenerator[AsyncSession]:
    """FastAPI dependency yielding a request-scoped async session."""
    async with _async_sessionmaker() as session:
        yield session
```

`expire_on_commit=False` is mandatory: the SQLAlchemy default (`True`)
refreshes loaded attributes after `commit()`, which becomes a sync I/O call
under async and raises `MissingGreenlet` (Pitfall 8 in 06-RESEARCH.md).

**Apple Silicon greenlet pull:** SQLAlchemy auto-installs `greenlet` only
on linux-x86_64, ppc64le, aarch64, AMD64, and win32. macOS arm64
(`platform.machine() == "arm64"`) is NOT in that marker set, so
`sqlalchemy[asyncio]>=2.0.50` is added explicitly to `pyproject.toml`
runtime deps to make the install platform-agnostic. Without this, the
first `await session.execute(...)` raises
`ValueError: the greenlet library is required to use this function`.

**Settings additions (Phase 6 D-01, D-11):**

```python
class Settings(BaseSettings):
    ...
    database_url: str = "postgresql+psycopg://trip_planner:trip_planner@localhost:5432/trip_planner"
    db_pool_size: int = 5
    db_pool_overflow: int = 10
    seed_allow_non_local: bool = False
```

These live on `Settings` per CLAUDE.md ("Tunable thresholds live on
Settings, not as module-level constants"). `seed_allow_non_local` lands
here so its env-var override is wired now; Plan 06-06 enforces it when
the seed flow lands. `Settings.auth_users` is intentionally retained in
this plan — Plan 06-04 owns its deletion alongside `EnvUserRepository`
removal so the running app stays bootable while the intermediate plans
land.

**Event-log schema (D-02 — verbatim from CONTEXT.md):**

```
message(
  id              BIGSERIAL PRIMARY KEY,
  conversation_id UUID NOT NULL REFERENCES conversation(id) ON DELETE CASCADE,
  seq             INTEGER NOT NULL,
  payload         JSONB NOT NULL,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX message_conv_seq ON message(conversation_id, seq);
```

Each PydanticAI `ModelMessage` serializes to one row via
`to_jsonable_python(msg)` and deserializes via
`ModelMessagesTypeAdapter.validate_python(rows)`. Replay is
`SELECT payload FROM message WHERE conversation_id = $1 ORDER BY seq`.
The `(conversation_id, seq) UNIQUE` index converts concurrent appends
into a clean `IntegrityError` the caller can map to a 409 / `ErrorEvent`
(Pitfall 6 — single-writer-per-conversation is the v1 invariant).

**ABC seams (D-05, D-06):**

Phase 6 splits the existing `ConversationStore` ABC into two
narrower abstractions, both wired via `app.state` singletons in the
FastAPI lifespan:

- `MessageStore(ABC)` (D-05) — events: `append`, `load`, `delete`, plus
  `first_user_message_preview` (replaces the Phase 5 `getattr(_store)`
  peek noted in 06-PATTERNS.md). Phase 6 ships `InMemoryMessageStore`
  (used by unit tests + dev fallback) and `PostgresMessageStore`.
- `ConversationRepository(ABC)` (D-06) — meta CRUD: `create`, `get`,
  `list_for_user`, `bump_last_activity`, `delete`. Ships `InMemory` +
  `Postgres` impls.

Both ABCs are `class Foo(ABC)` per CLAUDE.md ("Abstract interfaces use
`ABC`, never `Protocol`"). `ChatService.__init__` accepts both via DI;
swapping in `RedisMessageStore` or `HybridMessageStore` later requires
zero changes to `ChatService`.

**Redis deferral (D-04):**

No Redis in Phase 6 — compose ships only the `db` service. v1 is
documented as single-replica. Triggers for adding Redis later
(multi-replica deploy, hot-path conversation-meta read latency,
cross-pod active-stream tracking) are explicitly captured in
CONTEXT.md `<deferred>` so the future phase can pick up the work
without re-litigating the rationale. The ABC seams above are what
makes that future addition non-disruptive.

## Verification

The Wave 0 spike at `backend/tests/unit/db/test_db_session.py` exercises
three behaviors:

| Test | Assertion | DB needed? |
|------|-----------|------------|
| `test_engine_url_uses_psycopg_async_dialect` | `str(engine.url)` starts with `postgresql+psycopg://` | No |
| `test_async_sessionmaker_disables_expire_on_commit` | `_async_sessionmaker.kw["expire_on_commit"] is False` (Pitfall 8 lock) | No |
| `test_async_session_select_one_round_trip` | Open `AsyncSession`, `await session.execute(text("SELECT 1"))`, assert `scalar_one() == 1`; skip cleanly on `OperationalError` | Yes (Postgres 16 on `localhost:5432`) |

The third test was run against `postgres:16-alpine` started via
`docker run --rm -p 5432:5432 -e POSTGRES_PASSWORD=trip_planner
-e POSTGRES_USER=trip_planner -e POSTGRES_DB=trip_planner postgres:16-alpine`
during Plan 06-01 execution — all three pass. Without Postgres, the
third test skips with a documented message; the first two still pass
deterministically. Path-based test selection per CLAUDE.md keeps the
file under `tests/unit/db/` with no `pytest.mark.unit` decorator.

## Consequences

**Code surface (Phase 6 plans):**

- **Plan 06-01 (this plan)**: `pyproject.toml` deps pinned + lockfile
  regenerated; `app/db/__init__.py` + `app/db/session.py` shipped;
  `Settings.database_url`, `db_pool_size`, `db_pool_overflow`,
  `seed_allow_non_local` added; spike smoke test passes; this ADR locks.
- **Plan 06-02**: `app/db/models.py` SQLModel tables (`User`,
  `Conversation`, `Message`); `alembic init -t async`; first
  `--autogenerate` migration committed.
- **Plan 06-03**: `MessageStore` + `ConversationRepository` ABCs +
  `InMemory*` + `Postgres*` impls; `ChatService` constructor swap;
  lifespan wiring.
- **Plan 06-04**: `PostgresUserRepository` replaces `EnvUserRepository`;
  `Settings.auth_users` deleted; auth routes unchanged through the ABC.
- **Plan 06-05**: codebase-wide `session` → `conversation` rename
  (D-03); SSE wire format guard regenerated under `conversation_id`;
  frontend types + hooks coordinated in the same atomic PR.
- **Plan 06-06**: `docker-compose.yml`, justfile recipes
  (`compose-up`, `compose-down`, `migrate`, `db-seed`), `scripts/seed.py`
  with `seed_allow_non_local` enforcement, `seed.toml.example`.

**Closes** (carry-forward from CONTEXT.md / 06-RESEARCH.md):

- D-01 spike: VERIFIED (3/3 tests pass against live Postgres 16; the
  asyncpg fallback path is **not** taken).
- ARCHITECTURE.md "Pending ADR-006" entry — this file fills it.
- 06-PATTERNS.md `getattr(self._conversation_store, "_store", None)`
  anti-pattern (CR-04) — the new `MessageStore.first_user_message_preview`
  method on the ABC is the recorded fix; Plan 06-03 lands the impls.

**Wire format:**

- SSE event JSON stays byte-identical until Plan 06-05's rename. The
  Phase 5 wire-format golden file at
  `tests/unit/chat/test_stream_event_wire_compat.py` is the gate; it
  regenerates under `conversation_id` in Plan 06-05.

**Test posture:**

- Path-based selection per CLAUDE.md (`tests/unit/db/`,
  `tests/integration/db/`). The spike test under `tests/unit/db/` skips
  cleanly when Postgres is absent so CI without compose passes; running
  with compose up makes it pass. Plan 06-03 introduces a per-test
  `pytest-postgresql` `postgresql_noproc` fixture pointed at the
  compose `db` for repository-level tests.

**Open risks** (carried forward to Plans 06-02 through 06-06):

- **OQ-R1** (from ADR-007): `ModelMessagesTypeAdapter` serialization
  may evolve between pydantic-ai minor versions. Plan 06-02 must store
  the pydantic-ai version alongside serialized messages — pencilled in
  for the `message.payload` envelope decision.
- **WR-01** (from Phase 5 verification + Pitfall 6): concurrent
  `chat_stream` calls on the same conversation race the unique
  `(conversation_id, seq)` index. Plan 06-03 adds an integration test
  that asserts the unique-violation surfaces as a clean
  `IntegrityError` mapped to a 409 / `ErrorEvent`. Multi-writer
  serialization (advisory locks or `SELECT FOR UPDATE`) is deferred
  per D-04.
- **PG14-not-supported**: The schema relies on `gen_random_uuid()`
  in core. Postgres 13+ ships it without `pgcrypto`; the locked image
  is `postgres:16-alpine` so this is fine, but a deployment that swaps
  to Postgres 12 would break.
- **macOS x86_64**: The greenlet platform-marker workaround (explicit
  `sqlalchemy[asyncio]`) is needed on Apple Silicon; macOS x86_64 is
  in the auto-marker set so the explicit dep is redundant but
  harmless there. CI on linux-x86_64 likewise unaffected.

## Alternatives Considered

| Instead of | Could Have Used | Why Not |
|-----------|------------------|---------|
| `psycopg[binary,pool]` async | `asyncpg` | asyncpg is ~30% faster on raw queries but does not go through libpq, has slightly different parameter binding semantics, and SQLModel docs / `full-stack-fastapi-template` lean toward psycopg. Phase 6 traffic is dev-grade demo volume; perf delta is irrelevant. The D-01 spike confirms psycopg async works against the ChatService shape. |
| SQLModel | Two parallel classes (Pydantic v2 DTO + SQLAlchemy 2.0 mapped class) | One class, both surfaces. Phase 5 already pins `pydantic>=2.12`, so `sqlmodel>=0.0.38` (Pydantic 2.12+ fix landed in 0.0.32) is the right floor. |
| alembic with `--autogenerate` | Hand-written migrations | Hand-written is safer for prod schema changes but slower for greenfield. D-11 locks autogenerate; first migration is the full schema, subsequent ones are diffs against `SQLModel.metadata`. Operators inspect generated SQL before committing. |
| JSONB column for entire `message.payload` | Normalized parts table per `ModelMessage` part type (TextPart, ToolCallPart, …) | A normalized schema would make tool-call replay queryable in SQL but adds 5+ tables. D-02 already locks JSONB. Future agent-state phase may add a normalized projection table on top of the event log. |
| `expire_on_commit=False` set explicitly | Default `True` | Default breaks SSE streams (Pitfall 8) — any attribute access after commit triggers a sync refresh that raises `MissingGreenlet` under async. Mandatory lock on every async session. |
| `gen_random_uuid()` in core (Postgres 13+) | `uuid-ossp` extension v5 namespacing | Postgres 16 ships `gen_random_uuid()` in core. v5 namespaced UUIDs are unnecessary for v1; if needed later the extension is a one-line `CREATE EXTENSION` add. |
| `ABC` interfaces | `typing.Protocol` (structural subtyping) | Project rule (CLAUDE.md): `ABC` is the in-project convention; `Protocol` is reserved for third-party duck-typing compatibility only. ADR-007 locks the same convention for the LLM tier. |
| Redis in Phase 6 | Postgres-only persistence | Phase 6 single-replica scope means Postgres covers durability and meta writes. ABC seams (D-05, D-06) keep adding Redis later non-disruptive. |

## References

### Primary (HIGH confidence)

- [CITED: docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html] —
  `create_async_engine`, `async_sessionmaker`, `AsyncSession` lifecycle,
  AsyncEngine fork-safety. Drives the engine + sessionmaker shape in
  `app/db/session.py`.
- [CITED: docs.sqlalchemy.org/en/20/dialects/postgresql.html] —
  `postgresql+psycopg://` URL scheme; psycopg 3 listed as a
  first-class async driver alongside asyncpg.
- [CITED: alembic.sqlalchemy.org/en/latest/cookbook.html#using-asyncio-with-alembic]
  — async `env.py` template (`alembic init -t async`) referenced by
  Plan 06-02.
- [CITED: github.com/fastapi/sqlmodel sqlmodel/ext/asyncio/session.py]
  — SQLModel's AsyncSession subclass with `.exec()`. Confirms the
  import path used by `app/db/session.py`.
- [CITED: github.com/fastapi/sqlmodel/releases] — 0.0.32 added
  Pydantic 2.12+ `Annotated` support; 0.0.38 latest as of 2026-06-03.
- [CITED: github.com/fastapi/full-stack-fastapi-template/blob/master/backend/app/alembic/env.py]
  — `target_metadata = SQLModel.metadata` pattern after importing
  every model module; used by Plan 06-02.
- [CITED: pydantic.dev/docs/ai/core-concepts/message-history/] —
  `ModelMessagesTypeAdapter.validate_python` + `pydantic_core.to_jsonable_python`
  round-trip used by `MessageStore.append` / `MessageStore.load`.
- [CITED: postgresql.org/docs/16/uuid-ossp.html] — `gen_random_uuid()`
  in core since PG 13.
- [CITED: pypi.org/project/pytest-postgresql] — `postgresql_noproc`
  fixture pointed at the compose `db` service; lands in Plan 06-03.

### Project

- `.planning/phases/06-postgres-redis-docker-compose/06-CONTEXT.md` —
  D-01 (spike), D-02 (event-log schema), D-04 (Redis deferral), D-05
  (`MessageStore` ABC), D-06 (`ConversationRepository` ABC), D-11
  (alembic from day 1).
- `.planning/phases/06-postgres-redis-docker-compose/06-RESEARCH.md` —
  Standard Stack table (verified versions), Pitfalls 1–8
  (SQLModel + Pydantic 2.12, autogenerate, pool exhaustion, port
  collision, BinaryContent bloat, concurrent appends, locale drift,
  expire_on_commit), Pattern 1 (async session) used verbatim.
- `.planning/phases/06-postgres-redis-docker-compose/06-PATTERNS.md` —
  ABC + DI override pattern; the `_store` peek anti-pattern fix.
- `.planning/adrs/ADR-007-pydantic-ai.md` — agent runtime contract
  Phase 6 must preserve; declares OQ-R1 (`ModelMessagesTypeAdapter`
  evolution risk) inherited here.
- `backend/app/chat/store.py` — Phase 5 `ConversationStore(ABC)` that
  D-06 splits into `MessageStore` + `ConversationRepository`.
- `backend/app/auth/repository.py` — `UserRepository(ABC)` +
  `EnvUserRepository` reference for Plan 06-04's
  `PostgresUserRepository`.
