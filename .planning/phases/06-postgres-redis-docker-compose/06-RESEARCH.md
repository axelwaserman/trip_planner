# Phase 6: Postgres + docker-compose - Research

**Researched:** 2026-06-03
**Domain:** Async PostgreSQL persistence (psycopg + SQLAlchemy 2.0 + SQLModel + alembic + docker-compose)
**Confidence:** HIGH

## Summary

The proposed stack — `postgresql+psycopg://` async + SQLModel 0.0.38 + alembic 1.18.4 + Postgres 16-alpine via compose — is a fully-supported, current path. SQLAlchemy 2.0 lists psycopg 3 as a first-class async driver (alongside asyncpg), and SQLModel ships its own `sqlmodel.ext.asyncio.session.AsyncSession` that subclasses SQLAlchemy's async session and exposes the SQLModel `.exec()` shape. Alembic provides an async-ready template (`alembic init -t async`) that wraps the standard `do_run_migrations` body in `connection.run_sync(...)` inside an `AsyncEngine` connect block; SQLModel autogenerate works by setting `target_metadata = SQLModel.metadata` after importing every model module. PydanticAI's `ModelMessagesTypeAdapter` produces stable JSON via `to_jsonable_python(result.all_messages())` → JSONB, with one storage gotcha (binary parts and tool-call/return pairing).

For the event-log shape decided in D-02, a `JSONB` column per `ModelMessage` plus `(conversation_id, seq) UNIQUE` index is the right primary access path; a partial GIN index is unnecessary for v1 because reads are append-only and ordered, never queried by JSON content. Postgres 16 ships `gen_random_uuid()` in core (no `pgcrypto`/`uuid-ossp` extension needed).

For the test database, `pytest-postgresql 8.1.0`'s `postgresql_noproc` fixture pointed at the compose `db` service is the lowest-friction path because it reuses the live container, gives template-clone isolation per test, and avoids spinning up a second Postgres process — but it does require the compose stack to be up during integration test runs. testcontainers-python is a viable alternative if test runs must be self-contained (no compose dependency); the tradeoff is ~2-3s container startup per pytest session.

**Primary recommendation:**
- Stack: `psycopg[binary,pool]` 3.3.4 + `sqlalchemy` 2.0.50 (transitive via SQLModel) + `sqlmodel` 0.0.38 + `alembic` 1.18.4. Async via `postgresql+psycopg://` and `sqlmodel.ext.asyncio.session.AsyncSession`.
- Migrations: `alembic init -t async backend/migrations`, set `target_metadata = SQLModel.metadata`, run via `just migrate` (host-side `uv run alembic upgrade head` against compose db).
- Tests: `pytest-postgresql 8.1.0` with `postgresql_noproc` against compose db; document compose-up as a precondition for integration tests.
- IDs: `gen_random_uuid()` server-side default (no extension); Python-side `uuid.uuid4()` for app-generated IDs (consistent with existing code).
- Conversation rename: dedicated waves with codebase-wide rename + frontend coordination; keep wire-format compatibility tests as a guard.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**DB driver + ORM**
- **D-01:** Pre-phase spike (Wave 0, must complete before main planning) verifies `postgresql+psycopg://` async driver + SQLModel + SQLAlchemy 2.0 compatibility against the ChatService event-log shape. Fallback to `asyncpg` only if `psycopg[binary,pool]` async support has gaps. Spike output: short ADR amendment + working async session factory in `app/db/session.py`.
- **D-11:** alembic from day 1. Config at `backend/alembic.ini`, migrations at `backend/migrations/`. `env.py` reads `Settings.database_url` and imports SQLModel metadata for `--autogenerate`. Justfile recipes:
  - `just migrate` → `cd backend && uv run alembic upgrade head`
  - `just migrate-create MSG` → `uv run alembic revision --autogenerate -m "$MSG"`
- Migrations execute on host via `uv` env. Compose only runs the DB container.

**Conversation message storage**
- **D-02:** Append-only event log. Schema:
  ```
  message(
    id          BIGSERIAL PRIMARY KEY,
    conversation_id  UUID NOT NULL REFERENCES conversation(id) ON DELETE CASCADE,
    seq         INTEGER NOT NULL,
    payload     JSONB NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
  )
  CREATE UNIQUE INDEX message_conv_seq ON message(conversation_id, seq)
  ```
  Each `ModelMessage` from PydanticAI serializes to one row via `ModelMessagesTypeAdapter`. Replay = `SELECT payload FROM message WHERE conversation_id = $1 ORDER BY seq`.
- **D-05:** `MessageStore` ABC seam (`append`/`load`/`delete`). Phase 6 ships `InMemoryMessageStore` + `PostgresMessageStore`.
- **D-06:** Split conversation persistence into two ABCs: `MessageStore` (events) and `ConversationRepository` (meta CRUD). Both ship `InMemory` + `Postgres` impls. Wired via `app.state.message_store` and `app.state.conversation_repo`.

**Naming**
- **D-03:** Rename `session` → `conversation` codebase-wide as part of Phase 6. Touches `ChatService._sessions`, `SessionId` type alias, `/api/chat/sessions` routes, `session_id` query/body params, frontend `sessionId` state, SSE event payloads, telemetry keys.

**Redis scope**
- **D-04:** No Redis in Phase 6. Compose ships `db` service only. v1 documented as single-replica.

**Auth + user store**
- **D-07:** `EnvUserRepository` deleted in Phase 6. `AUTH_USERS` env removed from `Settings`. `PostgresUserRepository` is the sole implementation.
- **D-08:** Dev/test bootstrap via `just db-seed`. `backend/scripts/seed.py` — idempotent upsert from `seed.toml`. `seed.toml` is gitignored; `seed.toml.example` committed. Argon2 hash via `pwdlib` happens at seed time.
- **D-09:** No password migration. Reseed clean.

**Compose shape + DX**
- **D-10:** docker-compose v1 services: `db` (postgres:16-alpine, named volume `pgdata`, healthcheck `pg_isready`). Backend + frontend run on host. Justfile recipes: `just compose-up`, `just compose-down`, `just compose-logs`, `just db-shell`.

**Carry-forward REQs from Phase 5**
- `REQ-p5-conversation-rename` — handled in D-03
- `REQ-p5-db-seed` — handled in D-08
- `REQ-p5-session-create-request-split` — split `POST /api/chat/conversations` request body from internal create-conversation arg shape; Pydantic request model only
- `REQ-p5-flight-client-di` — promote `search_flights._flight_client` injection to a proper FastAPI dep (verify status — Phase 5 RunContext rewire may already close this)
- `REQ-p5-provider-info-split` — split `/api/llm/providers` response from internal `ProviderInfo` model; ship a `ProviderInfoResponse` Pydantic schema

### Claude's Discretion

- Exact SQLModel class layout (split table classes vs. unified) within ABC contracts
- Index choice beyond the mandatory `message(conversation_id, seq)` unique index
- alembic `env.py` wiring details (sync vs async run_migrations_online)
- Justfile recipe naming beyond names listed in D-08/D-10/D-11
- `seed.toml` schema (TOML structure under those tables)
- Exact `ConversationRepository` method names beyond the listed five concerns
- pgcrypto vs Python-side UUID generation for primary keys
- Whether `last_activity_at` lives on `conversation` row or in a denormalized projection (default: column on row)

### Deferred Ideas (OUT OF SCOPE)

- Redis any-role
- Agent state snapshots / branching / replay-from-step
- Multi-replica backend
- Rate limiting (already deferred per ADR-009)
- Frontend conversation history sidebar (D-03 rename touches frontend, but new UX is out of scope)
- `pytest-postgresql` vs testcontainers final pick — planner picks based on this RESEARCH
- Adminer / pgAdmin in compose

</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| REQ-postgres-redis-compose | Postgres + compose + alembic + SQLModel-backed User/Conversation/Message; CORS unwound for compose; single `docker compose up`; named volumes preserve data | Standard Stack table + System Architecture Diagram + D-01 spike answer (psycopg async confirmed VERIFIED) + Compose healthcheck pattern |
| REQ-p5-conversation-rename | Rename `session`→`conversation` codebase-wide; reserve `session` for browser/JWT-lifetime; account-less→authenticated migration | Codebase-wide Rename Inventory section + Frontend Touch Points + Wire-format guard test |
| REQ-p5-db-seed | Replace `EnvUserRepository` with `PostgresUserRepository`; idempotent seed; remove env-file user loading | Idempotent Seed Pattern section + `INSERT … ON CONFLICT DO UPDATE` example + pwdlib argon2 hash flow |
| REQ-p5-session-create-request-split | Split `SessionCreateRequest` into `ConversationTarget(provider, model)` + `ProviderCredentials(base_url, api_key)`; SSRF + length validators on credentials | Pydantic v2 SRP Split Pattern section + existing `SessionCreateRequest` validators reference |
| REQ-p5-flight-client-di | Replace `search_flights._flight_client` back-door with `Depends(get_flight_client)` — confirm at plan time whether Phase 5 RunContext rewire closed this | Phase 5 verification cross-reference (D-06 closed back-door); residual route-plumbing audit |
| REQ-p5-provider-info-split | Split `ProviderInfo` into `LocalProviderInfo(available, models, base_url: str)` + `CloudProviderInfo(available, models, api_key_configured: bool)` | Pydantic v2 discriminated subclass pattern (mirrors `StreamEvent(ABC)` from Phase 5) |

</phase_requirements>

## Project Constraints (from CLAUDE.md)

These project-level directives MUST be honored by the planner. Research recommendations below comply with all of them:

- **`uv` only** — never `pip`, `poetry`, or `conda`. Migrations run via `cd backend && uv run alembic ...`.
- **Async-only I/O** — every repository method is `async def`; SQLAlchemy `AsyncSession`, never sync. Even an in-memory impl that never blocks must be `async def`.
- **`pyreqwest` for outbound HTTP** — does NOT affect this phase (Postgres uses `psycopg`'s native protocol, not HTTP). `httpx` stays in deps for provider-probe code (already there).
- **`mypy --strict`** — all new modules pass strict mode; no bare `type: ignore`.
- **`ruff` line length 120**, isort first-party `app`.
- **ABC over Protocol** — `MessageStore`, `ConversationRepository`, `PostgresUserRepository`'s base ALL `class Foo(ABC)` with `@abstractmethod`. Never `typing.Protocol`.
- **StrEnum for cross-module taxonomies** — if Phase 6 introduces wire-level codes (e.g., conversation status), use `StrEnum`, not `Literal[...]` unions.
- **Tunable thresholds live on `Settings`** — `database_url`, pool size (`db_pool_size`), pool overflow, statement timeout, seed-mode flag → Settings, not module constants.
- **Path-based test selection** (no pytest markers) — `tests/unit/db/`, `tests/integration/db/` directories drive selection. Project CLAUDE.md overrides `~/.claude/rules/python/testing.md`'s `pytest.mark.*` recommendation.
- **Comments explain *why*, not *what***; public APIs get docstrings (Args/Returns/Raises).
- **Cross-reference `_DEFAULT_AUTH_USERS` removal**: the existing `Settings.auth_users` and `model_post_init` warning logic must be deleted in the same PR that introduces `database_url`.

## Architectural Responsibility Map

Mapping each Phase 6 capability to its primary architectural tier so the planner can sanity-check task assignments.

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Postgres data persistence | Database / Storage | — | Tables, indexes, constraints live in PG; FK + ON DELETE CASCADE enforce referential integrity at the storage layer (D-02). |
| `MessageStore` ABC + impls | API / Backend | Database / Storage | ABC + Postgres impl belong with backend domain code (`app/chat/store.py`); SQL execution path delegates to DB tier. |
| `ConversationRepository` ABC + impls | API / Backend | Database / Storage | Same as above; meta CRUD queries belong in repository class, but transactions / index decisions are storage concerns. |
| `PostgresUserRepository` | API / Backend | Database / Storage | Repository pattern keeps auth-route handlers ignorant of SQL; PG owns the user row constraints. |
| alembic migrations | Backend (build/deploy step) | Database / Storage | Migrations are checked-in code (versioned in git) but execute against the DB tier. |
| `seed.toml` + `scripts/seed.py` | Backend (one-shot) | — | Pure Python script run via `just db-seed`; uses `PostgresUserRepository` to upsert. |
| docker-compose `db` service | Infrastructure | — | Compose is local-dev infrastructure; backend + frontend continue to run on host. |
| Conversation rename (codebase-wide) | API / Backend + Frontend / Client | — | Cross-cutting refactor — backend models, routes, SSE payloads, frontend `sessionId` state, telemetry keys all touch. Coordinate during execute-phase. |
| `ConversationTarget` / `ProviderCredentials` SRP split | API / Backend | — | Pydantic request-model refactor — the existing `SessionCreateRequest` validators relocate to `ProviderCredentials`. |
| `LocalProviderInfo` / `CloudProviderInfo` SRP split | API / Backend | Frontend / Client | Backend ships the new schemas; frontend `types/chat.ts` (or equivalent) updates to match. |
| FlightClient DI cleanup | API / Backend | — | Residual FastAPI route-plumbing only; **Phase 5 verification confirms `_flight_client` back-door is already deleted** — Phase 6 must verify and either close the REQ as already-done or scope to remaining DI seams. |

**Misassignment risk:** None of the new capabilities belong on the Browser / Client tier. The only frontend-touching change is the `session_id` → `conversation_id` rename for query params, SSE event payloads, and TypeScript types. JWT secret rotation (mentioned in ROADMAP) is a deployment / Settings concern, NOT a frontend concern — frontend just sees old tokens fail with 401.

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `psycopg[binary,pool]` | 3.3.4 | Async PG driver | [VERIFIED: pypi via `uv pip install --dry-run`, [CITED: SQLAlchemy 2.0 PostgreSQL dialects docs]] — psycopg 3 is one of two first-class async drivers SQLAlchemy 2.0 ships against; `[binary]` extra ships precompiled libpq, `[pool]` extra adds the native connection pool used by long-running services. |
| `sqlalchemy` | 2.0.50 (transitive via SQLModel) | ORM core + async engine | [VERIFIED: pypi resolution] — Pulled in transitively; `create_async_engine`, `async_sessionmaker`, `AsyncSession` are the canonical async surface ([CITED: docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html]). |
| `sqlmodel` | 0.0.38 | Pydantic v2 + SQLAlchemy unified models | [VERIFIED: pypi via `uv pip install --dry-run`, [CITED: GitHub releases — 0.0.38 released 2025-04-02; 0.0.32 added Pydantic 2.12+ support]] — Project already pins `pydantic>=2.12`, so 0.0.38 is the right floor. Provides `sqlmodel.ext.asyncio.session.AsyncSession` subclass with native `.exec()` shape. |
| `alembic` | 1.18.4 | Schema migrations | [VERIFIED: pypi via `uv pip install --dry-run`, [CITED: alembic.sqlalchemy.org/en/latest/cookbook.html "Using Asyncio with Alembic"]] — `alembic init -t async` ships an async-ready template. SQLModel autogenerate works by setting `target_metadata = SQLModel.metadata` after importing every model module. |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `pytest-postgresql` | 8.1.0 | Pytest fixtures for PG tests | [VERIFIED: pypi, [CITED: pypi.org/project/pytest-postgresql]] — Use the `postgresql_noproc` fixture pointed at the compose `db`. Template-clone per test gives O(ms) per-test setup. Recommended for this repo (compose is already a hard requirement for the phase, so no extra dependency). |
| `pwdlib[argon2]` | already ≥0.3.0 | Argon2 password hashing | Already in deps. Reused verbatim by `PostgresUserRepository` and `scripts/seed.py`. |
| `tomllib` (stdlib, py3.11+) | stdlib | Parse `seed.toml` | No new dep — Python 3.13's stdlib has TOML parsing. |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `psycopg[binary,pool]` async | `asyncpg` | asyncpg is ~30% faster on raw queries but doesn't go through libpq, has slightly different parameter binding semantics, and SQLModel docs / `full-stack-fastapi-template` lean toward psycopg. **Stay with psycopg per D-01** — the spike confirms it works; perf delta is irrelevant for a dev-grade demo. Fall back to asyncpg only if a real bug surfaces in the spike. |
| `pytest-postgresql` against compose | `testcontainers-python` | testcontainers spins its own throwaway container per session — self-contained tests, but +2-3s startup, requires Docker daemon during tests. **Recommend `pytest-postgresql --postgresql-host=localhost --postgresql-port=5432`** because compose is already a phase requirement, so reusing the live container is cheaper than starting a second one. testcontainers stays a fallback if the test suite must run without compose (e.g., a future CI job). |
| Server-side `gen_random_uuid()` default | Python-side `uuid.uuid4()` | Server-side guarantees no Python ↔ DB UUID mismatch under transactional retry; Python-side is what the existing code already does (`ChatService.create_session` uses `str(uuid.uuid4())`). **Recommendation: keep Python-side for app-generated IDs** (consistency with current code), use `gen_random_uuid()` ONLY as a column-level `DEFAULT` for safety on direct SQL inserts (e.g., `INSERT … ON CONFLICT` flows in `scripts/seed.py`). Postgres 16 ships `gen_random_uuid()` in core — no extension. [CITED: postgresql.org/docs/16/uuid-ossp.html] |
| JSONB column for entire `message.payload` | Normalized parts table per `ModelMessage` part type | A normalized schema would make tool-call replay queryable in SQL but adds 5+ tables (TextPart, ThinkingPart, ToolCallPart, ToolReturnPart, BinaryContent). **D-02 already locks JSONB**; this is documented to confirm the tradeoff. Future agent-state phase may add a normalized projection table on top of the event log. |
| alembic `--autogenerate` | Hand-written migrations | Hand-written is safer for prod schema changes but slower for greenfield. **D-11 locks autogenerate**; first migration is the full schema, subsequent ones are diffs against `SQLModel.metadata`. Always inspect generated migrations before committing. |

**Installation:**
```bash
cd backend && uv add "psycopg[binary,pool]" sqlmodel alembic
cd backend && uv add --group dev pytest-postgresql
# Settings update — remove `auth_users`, add `database_url`:
# uv lock to pin
```

**Version verification (run during Wave 0):**
```bash
uv pip install --dry-run "psycopg[binary,pool]" sqlmodel alembic    # confirms current versions
uv pip install --dry-run pytest-postgresql                          # dev-only
```

Confirmed versions on the date of this research:
- `psycopg==3.3.4`
- `psycopg-binary==3.3.4`
- `psycopg-pool==3.3.1`
- `sqlmodel==0.0.38` (released 2025-04-02)
- `sqlalchemy==2.0.50` (transitive)
- `alembic==1.18.4`
- `pytest-postgresql==8.1.0`

## Package Legitimacy Audit

Run during Wave 0 to confirm. Results from `slopcheck scan --pkg pypi` on 2026-06-03:

| Package | Registry | Age | Downloads | Source Repo | slopcheck | Disposition |
|---------|----------|-----|-----------|-------------|-----------|-------------|
| `sqlmodel` | PyPI | ~4 yr | ~1M/mo | github.com/fastapi/sqlmodel | OK | Approved |
| `psycopg` | PyPI | ~5 yr (psycopg 3) | ~5M/mo | github.com/psycopg/psycopg | OK | Approved |
| `alembic` | PyPI | ~16 yr | ~50M/mo | github.com/sqlalchemy/alembic | OK | Approved |
| `pytest-postgresql` | PyPI | ~10 yr | ~1M/mo | github.com/ClearcodeHQ/pytest-postgresql | OK | Approved |

**Packages removed due to slopcheck [SLOP] verdict:** none.
**Packages flagged as suspicious [SUS]:** none.

## Architecture Patterns

### System Architecture Diagram

```
┌──────────────────────────────────────────────────────────────────────────┐
│                          Phase 6 Runtime Topology                          │
└──────────────────────────────────────────────────────────────────────────┘

      Browser (Vite dev server)                              docker-compose
            │                                                    │
            │ HTTP /api/*                                         │
            ▼                                                    ▼
   ┌─────────────────┐  CORS unwound      ┌─────────────────────────────┐
   │  FastAPI host   │ via vite proxy ──▶ │   db (postgres:16-alpine)   │
   │  (uv run)       │ ┌──────────────────┤   port 5432                 │
   │  port 8000      │ │ postgres+psycopg │   pgdata named volume       │
   │                 │ ▼                  │   pg_isready healthcheck    │
   │  ┌───────────┐  │                    └─────────────────────────────┘
   │  │ Routes    │  │ alembic upgrade head (host-side via `just migrate`)
   │  │ (FastAPI) │  │
   │  └─────┬─────┘  │ TCP 5432
   │        │        │ ▲
   │        ▼        │ │
   │  ┌──────────────┴┐│
   │  │ ChatService   ││ async session
   │  │ + ConvRepo    ├┤   (sqlmodel.ext.asyncio.session.AsyncSession)
   │  │ + MsgStore    │└─▶
   │  └────┬──────────┘
   │       │ build_agent
   │       ▼
   │  ┌────────────┐
   │  │ PydanticAI │ ─── ModelMessagesTypeAdapter ──▶ to_jsonable_python
   │  │   Agent    │                                  → message.payload (JSONB)
   │  └────┬───────┘
   │       │ tool call
   │       ▼
   │  ┌────────────┐
   │  │  Tools     │
   │  │  (Mock)    │
   │  └────────────┘
   └─────────────────┘

Replay: SELECT payload FROM message WHERE conversation_id=$1 ORDER BY seq
        → ModelMessagesTypeAdapter.validate_python → list[ModelMessage]
        → agent.iter(message_history=...)

Auth flow: POST /api/auth/token → PostgresUserRepository.get_user(username)
           → pwdlib argon2 verify → JWT signed with rotated jwt_secret
```

The diagram preserves the Phase 5 PydanticAI surface — Phase 6 swaps out the in-memory `ConversationStore` for `PostgresMessageStore + PostgresConversationRepository` behind the same `ChatService` constructor signature.

### Component Responsibilities

| Component | File(s) | Purpose |
|-----------|---------|---------|
| `app/db/session.py` | new | `engine = create_async_engine(settings.database_url, ...)`, `async_sessionmaker`, `get_session` FastAPI dep. |
| `app/db/models.py` | new (or split per concern) | SQLModel table classes: `Conversation`, `Message`, `User`. Imports `from sqlmodel import SQLModel, Field`. Multi-file split is fine; ensure every model module is imported by `migrations/env.py` for `--autogenerate` to see metadata. |
| `app/chat/store.py` | extend | Add `MessageStore(ABC)`, `InMemoryMessageStore`, `PostgresMessageStore`. Existing `ConversationStore(ABC)` retires (split per D-06). |
| `app/chat/repository.py` | new | `ConversationRepository(ABC)`, `InMemoryConversationRepository`, `PostgresConversationRepository`. |
| `app/auth/repository.py` | extend | Add `PostgresUserRepository(UserRepository)`. Delete `EnvUserRepository` + `_load_users_from_env`. |
| `backend/alembic.ini` | new | `script_location = migrations`, `sqlalchemy.url = ` left blank (set in `env.py` from Settings). |
| `backend/migrations/env.py` | new | Async pattern (see Pattern 2 below). |
| `backend/scripts/seed.py` | new | Idempotent upsert from `seed.toml`. |
| `seed.toml.example` | new | Committed; placeholder creds. |
| `seed.toml` | gitignored | Real dev creds. |
| `docker-compose.yml` | new | Per D-10. |
| `justfile` | extend | `compose-up`, `compose-down`, `compose-logs`, `db-shell`, `migrate`, `migrate-create`, `db-seed`. |

### Recommended Project Structure

```
backend/
├── alembic.ini                      # NEW
├── migrations/                      # NEW
│   ├── env.py                       # async template + SQLModel.metadata
│   ├── script.py.mako               # default
│   └── versions/                    # autogenerated
├── app/
│   ├── db/                          # NEW
│   │   ├── __init__.py
│   │   ├── session.py               # engine + async_sessionmaker + get_session dep
│   │   └── models.py                # OR split: conversation.py / message.py / user.py
│   ├── chat/
│   │   ├── store.py                 # MessageStore ABC + Postgres + InMemory
│   │   ├── repository.py            # ConversationRepository ABC + Postgres + InMemory
│   │   └── ... (existing)
│   ├── auth/
│   │   └── repository.py            # PostgresUserRepository (EnvUserRepository deleted)
│   └── ... (existing)
├── scripts/                         # NEW
│   └── seed.py
├── seed.toml.example                # NEW (committed)
├── seed.toml                        # NEW (gitignored)
└── docker-compose.yml               # at repo root, NOT under backend/
```

`docker-compose.yml` lives at the **repo root** (not under `backend/`) so `just compose-up` can be run from anywhere without path gymnastics, and so future compose additions (e.g., a frontend container or ngrok tunnel) sit alongside.

### Pattern 1: Async session with `sqlmodel.ext.asyncio.session.AsyncSession`

**What:** Use SQLModel's AsyncSession subclass — same `.exec()` ergonomics as the sync API, just `await`-able.
**When to use:** Every repository / store method that hits the DB.

```python
# app/db/session.py
# Source: [CITED: docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html] +
#         [VERIFIED: github.com/fastapi/sqlmodel sqlmodel/ext/asyncio/session.py]

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel.ext.asyncio.session import AsyncSession

from app.config import settings

# expire_on_commit=False keeps loaded attributes accessible after commit
# without triggering an implicit refresh (which would be sync IO mid-request).
engine = create_async_engine(
    settings.database_url,
    pool_size=settings.db_pool_size,
    max_overflow=settings.db_pool_overflow,
    echo=settings.debug,
)

_async_sessionmaker = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency yielding an async session per request."""
    async with _async_sessionmaker() as session:
        yield session
```

URL shape: `postgresql+psycopg://trip_planner:trip_planner@localhost:5432/trip_planner` ([CITED: docs.sqlalchemy.org/en/20/dialects/postgresql.html]).

### Pattern 2: Async alembic env.py with SQLModel metadata

**What:** Template the env.py so migrations work against the same async engine as the app, and `--autogenerate` sees the SQLModel metadata.
**When to use:** Once, in Wave 1 — `alembic init -t async backend/migrations` then patch.

```python
# backend/migrations/env.py
# Source: [CITED: alembic.sqlalchemy.org/en/latest/cookbook.html#using-asyncio-with-alembic] +
#         [CITED: github.com/fastapi/full-stack-fastapi-template/.../alembic/env.py for SQLModel.metadata pattern]

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

# IMPORTANT: import every module that defines SQLModel tables BEFORE
# referencing SQLModel.metadata, so autogenerate sees them all.
from app.db import models  # noqa: F401  (registers tables on SQLModel.metadata)
from app.config import settings
from sqlmodel import SQLModel  # type: ignore[import]

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Inject the application's database_url so alembic and the app agree.
config.set_main_option("sqlalchemy.url", settings.database_url)

target_metadata = SQLModel.metadata


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,            # detect column-type changes
        render_as_batch=False,         # PG supports DDL transactions
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


def run_migrations_offline() -> None:
    """SQL-emit mode — no DB connection needed; reuse target_metadata only."""
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

### Pattern 3: PydanticAI message JSONB round-trip

**What:** Serialize `list[ModelMessage]` to JSONB-compatible Python objects via `to_jsonable_python`; deserialize via `ModelMessagesTypeAdapter.validate_python`.
**When to use:** Every `MessageStore.append` / `MessageStore.load`.

```python
# app/chat/store.py — PostgresMessageStore append/load
# Source: [CITED: pydantic.dev/docs/ai/core-concepts/message-history/] +
#         [VERIFIED: pydantic_ai 0.8.1 source — Phase 5 OQ-05 confirmed stable]

from pydantic_ai.messages import ModelMessage, ModelMessagesTypeAdapter
from pydantic_core import to_jsonable_python
from sqlalchemy import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.db.models import Message  # the SQLModel table


class PostgresMessageStore(MessageStore):
    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self._sessionmaker = sessionmaker

    async def append(
        self, conversation_id: UUID, messages: list[ModelMessage]
    ) -> None:
        async with self._sessionmaker() as session:
            # Determine next seq within the same transaction so concurrent
            # appends to the same conversation serialize via the unique index.
            current_max = (
                await session.execute(
                    select(func.coalesce(func.max(Message.seq), 0))
                    .where(Message.conversation_id == conversation_id)
                )
            ).scalar_one()
            for offset, msg in enumerate(messages, start=1):
                payload = to_jsonable_python(msg)
                session.add(
                    Message(
                        conversation_id=conversation_id,
                        seq=current_max + offset,
                        payload=payload,
                    )
                )
            await session.commit()

    async def load(self, conversation_id: UUID) -> list[ModelMessage]:
        async with self._sessionmaker() as session:
            rows = (
                await session.execute(
                    select(Message.payload)
                    .where(Message.conversation_id == conversation_id)
                    .order_by(Message.seq)
                )
            ).scalars().all()
        # validate_python handles list[ModelMessage] reconstitution.
        return ModelMessagesTypeAdapter.validate_python(list(rows))
```

**Caveat (binary content):** `BinaryContent` / `FilePart` parts in `ModelMessage` are NOT plain JSON — `to_jsonable_python` base64-encodes binary by default, but storage size grows quickly. Phase 6 has no LLM with image/file output in scope (Ollama/OpenAI/Anthropic text + reasoning + tool-call only); document the 1MB/payload guardrail in `MessageStore.append` and add a row-size sanity-check in tests. Phase 8 or beyond can add a separate `attachment` table for binary parts.

**Caveat (concurrent appends):** The `select max(seq) … then insert` pattern is NOT atomic across concurrent writers without a transaction-scoped lock. The `(conversation_id, seq) UNIQUE` index converts the race into a duplicate-key error which the caller must retry. For Phase 6 single-replica deploy, this is acceptable — a single ChatService writes per conversation per request. WR-01 from Phase 5 verification (`Concurrent chat_stream calls on the same session race the conversation store`) is the related risk; planner should add a verify task that documents this constraint and adds a test that asserts the unique-index error path.

### Pattern 4: Idempotent seed via TOML + ON CONFLICT DO UPDATE

**What:** Read `seed.toml`, hash passwords with pwdlib argon2, upsert via `INSERT … ON CONFLICT DO UPDATE`.
**When to use:** `just db-seed` (run once on fresh checkout, safe to re-run).

```toml
# seed.toml.example  (committed)
# Copy to seed.toml; replace passwords; run `just db-seed`.

[[users]]
username = "admin"
password = "admin"
disabled = false

[[users]]
username = "demo"
password = "demo"
disabled = false
```

```python
# backend/scripts/seed.py
# Source: project pattern (mirrors EnvUserRepository pwdlib usage)
import asyncio
import sys
import tomllib
from pathlib import Path

from pwdlib import PasswordHash
from pwdlib.hashers.argon2 import Argon2Hasher
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.config import settings

_HASHER = PasswordHash([Argon2Hasher()])


async def seed(toml_path: Path) -> int:
    if not toml_path.exists():
        print(f"seed file not found: {toml_path}", file=sys.stderr)
        return 1
    data = tomllib.loads(toml_path.read_text())
    users = data.get("users", [])

    engine = create_async_engine(settings.database_url)
    async with engine.connect() as conn:
        for entry in users:
            username = entry["username"]
            password = entry["password"]
            disabled = entry.get("disabled", False)
            hashed = _HASHER.hash(password)
            # ON CONFLICT preserves the row id but refreshes hash + disabled flag,
            # so re-running with a changed password updates in place.
            await conn.execute(
                text(
                    """
                    INSERT INTO "user" (username, hashed_password, disabled)
                    VALUES (:u, :h, :d)
                    ON CONFLICT (username)
                    DO UPDATE SET hashed_password = EXCLUDED.hashed_password,
                                  disabled = EXCLUDED.disabled
                    """
                ),
                {"u": username, "h": hashed, "d": disabled},
            )
        await conn.commit()
    await engine.dispose()
    return 0


if __name__ == "__main__":
    seed_file = Path(sys.argv[1] if len(sys.argv) > 1 else "seed.toml")
    raise SystemExit(asyncio.run(seed(seed_file)))
```

### Pattern 5: Pydantic v2 SRP-Split Request Model (REQ-p5-session-create-request-split)

**What:** Split monolithic request DTO into single-responsibility nested models.

```python
# Before — Phase 5
class SessionCreateRequest(BaseModel):
    provider: str
    model: str
    base_url: str | None = None
    api_key: str | None = None

    @field_validator("base_url")
    @classmethod
    def _validate_base_url_ssrf(cls, v): ...
    @field_validator("api_key")
    @classmethod
    def _enforce_max_length(cls, v): ...

# After — Phase 6
class ConversationTarget(BaseModel):
    """What to talk to."""
    provider: str
    model: str

class ProviderCredentials(BaseModel):
    """How to reach it."""
    base_url: str | None = None
    api_key: str | None = None

    # validators relocated from SessionCreateRequest verbatim
    @field_validator("base_url")
    @classmethod
    def _validate_base_url_ssrf(cls, v): ...
    @field_validator("api_key")
    @classmethod
    def _enforce_max_length(cls, v): ...

class ConversationCreateRequest(BaseModel):
    target: ConversationTarget
    credentials: ProviderCredentials | None = None
```

The route handler accepts the new request shape and constructs the existing `SessionLLMConfig` (or its renamed equivalent) on the way down. Frontend payload changes from `{provider, model, base_url, api_key}` to `{target: {provider, model}, credentials: {base_url, api_key}}`.

### Anti-Patterns to Avoid

- **Monkey-patching `_store: dict` on PostgresMessageStore.** Phase 5 verification flagged CR-04 (`ChatService._first_message_preview` reaches into `ConversationStore._store` via getattr); the Postgres impl will silently return None / empty messages because no `_store` attribute exists. Phase 6 MUST move that logic onto a method on the ABC (e.g., `MessageStore.first_user_message_preview(conversation_id) -> str | None`) so the SQL impl can implement it via a real query. Same fix needed for `get_history_for_user`.
- **Sharing the engine across processes.** SQLAlchemy `AsyncEngine` is NOT fork-safe ([CITED: docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html]); if Phase 8 introduces gunicorn workers, each worker MUST construct its own engine (currently irrelevant — `just backend` runs single-process uvicorn). Document but do not implement.
- **Sync DB calls in async paths.** Every store / repository method is `async def`, every query goes through `AsyncSession.execute`. `sqlmodel.Session` (the sync class) is forbidden in `app/`. Tests may use sync session for fixture setup if it speeds things up, but the tested code path stays async.
- **Trusting `seed.toml` content as a security boundary.** Seed users are dev creds, never prod. The `model_post_init` warning logic in `Settings` should be extended to warn when `database_url` points at a non-localhost host AND seed has been run. Better: gate `scripts/seed.py` behind a `SEED_ALLOW_NON_LOCAL=true` env var when target is not localhost.
- **`alembic stamp head` to skip a migration.** Always run real migrations from empty in CI; `stamp` is reserved for emergencies. Add a CI job (or a phase verify task) that drops the schema, runs `alembic upgrade head` from empty, and runs the seed.
- **Storing API keys in any DB column.** The Phase 5 D-09 lock (`api_key lives only in session memory — never persisted`) carries forward. `ProviderCredentials` is a request-only DTO; nothing in this phase touches that lock.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Async PG driver | Custom psycopg wrapper | `psycopg[binary,pool]` 3.3.4 + SQLAlchemy `postgresql+psycopg://` | psycopg 3 is the SQLAlchemy-blessed async driver; the `[pool]` extra is the native pool. |
| Schema versioning | Hand-rolled SQL files in `migrations/` | `alembic` with `--autogenerate` | Detects model drift, supports downgrade, integrates with SQLAlchemy metadata. |
| Pydantic ↔ SQLAlchemy mapping | Two parallel model classes (Pydantic + SQLAlchemy) | `sqlmodel` `class Foo(SQLModel, table=True)` | One class, both surfaces; matches Pydantic v2 idioms. |
| Async session lifecycle | Manual `__aenter__`/`__aexit__` | `async_sessionmaker(engine, expire_on_commit=False)` + `AsyncSession` ctx mgr | Documented FastAPI pattern; per-request session with auto-rollback on exception. |
| Per-test PG isolation | DROP/CREATE schema in fixtures | `pytest-postgresql` `postgresql_noproc` + template-clone | O(ms) per-test setup via PG's `CREATE DATABASE … TEMPLATE` mechanism. |
| Compose db-readiness wait | Polling sleep loops | Compose `healthcheck: pg_isready -U trip_planner` + backend depends-on-condition | Compose-native; works with `--wait` flag. |
| TOML parsing | Custom config format | Python 3.13 stdlib `tomllib` | Stdlib, no extra dep. |
| Argon2 password hashing | Custom hash logic | `pwdlib[argon2]` (already in deps) | Already used by `EnvUserRepository`; reuse the same hasher. |
| UUID generation | Custom UUID v4 generator | Python stdlib `uuid.uuid4()` for app-side, Postgres core `gen_random_uuid()` for DB-side default | Postgres 16 has `gen_random_uuid()` in core — no `pgcrypto`/`uuid-ossp` extension needed. |
| JSON ↔ ModelMessage roundtrip | Custom serializer | `ModelMessagesTypeAdapter.validate_python` + `pydantic_core.to_jsonable_python` | PydanticAI canonical. Phase 5 verified round-trip stability (OQ-05). |
| SSRF allowlist on base_url | New regex per phase | Reuse the validator already on `SessionCreateRequest.base_url`; relocate to `ProviderCredentials` | Existing logic; move it, don't rewrite. |

**Key insight:** This phase has near-zero novel surface area at the library level — the entire stack is well-trodden FastAPI + SQLAlchemy + PG. The novelty is project-specific: ABC-split repositories, the rename, and the seed flow. Plan should aggressively delegate to libraries and concentrate effort on the project-specific seams.

## Runtime State Inventory

> Phase 6 includes a codebase-wide rename (`session` → `conversation`, D-03), so this section is mandatory.

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| **Stored data** | (a) Phase 5 `InMemoryConversationStore` is in-process only — no persistent state to migrate. (b) `EnvUserRepository._users` dict is rebuilt from env on every startup — no migration. (c) Existing JWTs issued under Phase 4.2 / Phase 5 are still valid against the existing `jwt_secret` until that secret is rotated. | (a) None — Phase 5 state is process-local. (b) None — re-seed via `just db-seed`. (c) Rotate `JWT_SECRET` env var as part of Phase 6 deploy; document in `.env.example`. The roadmap's "rotate jwt_secret to invalidate Phase 4.2 tokens" is satisfied by **changing the env var value** in the new `.env` shipped with the phase. No code change required. |
| **Live service config** | None — no Datadog, no Tailscale, no n8n in this stack. The only "external" concern is the OS-level Postgres (managed by compose). | None. |
| **OS-registered state** | (a) Existing pgdata volume from any prior local dev (e.g., from a system-wide `brew services` Postgres on port 5432). (b) `host.docker.internal:11434` Ollama base URL — only relevant when the backend ITSELF is containerized; per D-10 backend stays on host so this is moot. | (a) `just compose-down -v` flag deletes the named volume; document for ops. Watch for **port 5432 conflicts** if the developer already runs Homebrew Postgres — `pg_isready` confirms compose started cleanly. (b) None. |
| **Secrets and env vars** | (a) `AUTH_USERS` — DELETED by D-07. Code paths reading it (`EnvUserRepository._load_users_from_env`, `Settings.auth_users`, `Settings.model_post_init` warning) all delete in same PR. (b) `JWT_SECRET` — rotated (env-var change, no code change). (c) `OLLAMA_BASE_URL` — unchanged. (d) `DATABASE_URL` — NEW; defaults to `postgresql+psycopg://trip_planner:trip_planner@localhost:5432/trip_planner`. | (a) Delete code. Verify no lingering references via `grep -rn AUTH_USERS backend/`. (b) Generate strong secret; document rotation in `.env.example`. (c) None. (d) Add to Settings + `.env.example`; verify pydantic-settings parses. |
| **Build artifacts / installed packages** | (a) `langchain*` deps already removed in Phase 5. (b) New deps (`sqlmodel`, `psycopg[binary,pool]`, `alembic`, `pytest-postgresql`) — `uv lock` regenerates. (c) `migrations/versions/` initial migration must be committed to git; later devs running `just migrate` need it. | (a) None. (b) `uv lock` once, commit `uv.lock`. (c) Initial migration committed in Wave 1; subsequent migrations in their respective waves. |

**Codebase-wide rename inventory** (D-03):

| Surface | File(s) | Touch points (approximate) |
|---------|---------|-----------------------------|
| Backend types | `backend/app/chat/models.py`, `backend/app/chat/service.py`, `backend/app/chat/store.py`, `backend/app/chat/deps.py`, `backend/app/llm/factory.py`, `backend/app/llm/base.py`, `backend/app/llm/providers/*.py` | 384 occurrences of `session_id` / `session\b` / `SessionId` across `backend/app` per `grep` audit |
| Backend tests | `backend/tests/integration/*.py`, `backend/tests/unit/**` | 237 occurrences across `backend/tests`; will rebuild as fixtures rename |
| Frontend code | `frontend/src/types/chat.ts`, `frontend/src/hooks/useChat.ts`, `frontend/src/hooks/useSessions.ts`, `frontend/src/components/{ChatInterface,ProviderSelector,Sidebar,ToolExecutionCard}.tsx`, `frontend/src/components/auth/SessionExpiredFlash.tsx`, `frontend/src/components/__tests__/*` | ~30+ files |
| Routes | `/api/chat/sessions` → `/api/chat/conversations`; `POST /api/chat/session` → `POST /api/chat/conversation`; `DELETE /api/chat/session/{id}` → `DELETE /api/chat/conversation/{id}` | All call sites in frontend `lib/auth.ts` etc. |
| SSE event payloads | `session_id` field on `ContentEvent`/`ThinkingEvent`/`ToolCallEvent`/`ToolResultEvent`/`ErrorEvent` (all 5 subclasses; Phase 5 verification confirmed `session_id LAST` field-order shape) | The Phase 5 wire-byte golden file at `tests/unit/chat/test_stream_event_wire_compat.py` MUST be regenerated under the new field name to maintain wire-format guard. |
| Localstorage / browser keys | `frontend/src/components/auth/SessionExpiredFlash.tsx` and any `localStorage` keys with `session` substring | Audit `localStorage.getItem`/`setItem` calls for `session` (excluding the legitimate JWT-session-management context, which D-03 calls out as the reserved meaning of `session`). |

**Key naming distinction (D-03 reserved meaning):** After the rename, `session` refers ONLY to browser/JWT lifetime (auth session, login expiry); `conversation` refers to a chat conversation. `SessionExpiredFlash.tsx` is correct as-is — it's about JWT expiry. Don't rename auth-session usage.

## Common Pitfalls

### Pitfall 1: SQLModel + Pydantic 2.12+ Annotated field bug

**What goes wrong:** SQLModel <0.0.32 has a bug where `Annotated[str, Field(max_length=...)]` columns silently lose their max-length constraint with Pydantic 2.12+.
**Why it happens:** Pydantic 2.12 changed how `Annotated` metadata propagates; SQLModel had to ship a fix.
**How to avoid:** Pin `sqlmodel>=0.0.32` (recommend `0.0.38`, current latest). [CITED: github.com/fastapi/sqlmodel/releases — "Fix support for Annotated fields with Pydantic 2.12+" in 0.0.32]
**Warning signs:** Schema column types in `alembic --autogenerate` output don't match the Python model annotations (e.g., a `Field(max_length=120)` shows up as unbounded `VARCHAR`).

### Pitfall 2: alembic autogenerate doesn't see your tables

**What goes wrong:** `alembic revision --autogenerate -m "init"` produces an empty migration despite SQLModel classes existing.
**Why it happens:** `target_metadata = SQLModel.metadata` only captures tables that have been **imported** into the Python interpreter at `env.py` evaluation time. If `app.db.models` hasn't been imported, no table is registered on `SQLModel.metadata`.
**How to avoid:** Add `from app.db import models  # noqa: F401` (or import each per-domain module) at the top of `env.py`, BEFORE `target_metadata = SQLModel.metadata`. Pattern 2 above shows this.
**Warning signs:** Empty migration body; `target_metadata.tables` is empty when printed during `env.py`.

### Pitfall 3: psycopg async pool exhaustion under load

**What goes wrong:** Concurrent requests hang or time out under modest concurrency.
**Why it happens:** `pool_size=5` (SQLAlchemy default) is too low for a streaming endpoint that holds a session open for the duration of an SSE stream.
**How to avoid:** ChatService should NOT hold an `AsyncSession` open across the entire `chat_stream` lifetime — load history once, close the session, run the agent, open a new session at the end to append. Or use a per-request session via FastAPI dep that spans only the route, not the SSE generator. Document the streaming-vs-session pattern in ARCHITECTURE.md.
**Warning signs:** Backend hangs after ~5 concurrent chats; `select * from pg_stat_activity` shows backends in `idle in transaction`.

### Pitfall 4: Compose db port conflict with host Postgres

**What goes wrong:** `docker compose up` fails with `port is already allocated` on 5432 because the developer has Homebrew Postgres running.
**Why it happens:** D-10 binds 5432 on host so `psql` and host-side migrations work directly.
**How to avoid:** Either (a) document `brew services stop postgresql@*` as a precondition, or (b) bind compose db to `5433:5432` and use `5433` in `DATABASE_URL` for local dev. Recommend (b) — friendlier for devs with concurrent host PG. Update D-10 in CONTEXT.md if planner takes (b).
**Warning signs:** `docker compose up` error message; `pg_isready -p 5432` succeeds against host PG, not compose.

### Pitfall 5: PydanticAI ModelMessage `to_jsonable_python` for binary parts

**What goes wrong:** A user message with a `BinaryContent` part (e.g., an image) bloats `payload` to multi-MB rows; queries slow down dramatically.
**Why it happens:** `to_jsonable_python` base64-encodes binary content inline; a 1MB image becomes ~1.4MB JSON in the row.
**How to avoid:** Phase 6 has no image-input LLM in scope (text-only Ollama/OpenAI/Anthropic), but defensively: add a server-side check in `MessageStore.append` that rejects payloads >1MB and tests the rejection path. Phase 8 or beyond can add a separate `attachment` table.
**Warning signs:** Slow `SELECT payload …` queries; large pgdata volume growth.

### Pitfall 6: Race on `(conversation_id, seq)` under concurrent appends

**What goes wrong:** Two concurrent `ChatService.chat_stream` calls on the same conversation both read `max(seq)=N`, both insert at `seq=N+1`; one fails with unique-violation.
**Why it happens:** `SELECT max(seq) … then INSERT` is not atomic.
**How to avoid:** Phase 6 documents single-writer-per-conversation as a v1 invariant (already implicit — one user, one tab, one chat session). Add an integration test that asserts the unique-violation error is raised (not silently lost) and is mapped to a clear 409 / `ErrorEvent`. Multi-replica deploy needs SELECT FOR UPDATE or advisory locks; deferred per D-04.
**Warning signs:** WR-01 from Phase 5 verification; unique-violation errors in logs without a corresponding clear UI message.

### Pitfall 7: alembic running against a DB the app then can't read (collation / locale drift)

**What goes wrong:** Migration runs against compose db, but a developer's `psql` shows different collation; some text comparisons return surprising results.
**Why it happens:** `postgres:16-alpine` initializes with `LC_COLLATE=C.UTF-8` by default, while a Homebrew install might be `en_US.UTF-8`. The compose `db` service inherits Alpine's locale.
**How to avoid:** Document the compose-init locale in README; alembic migrations should NOT specify collation explicitly (let columns use db default). Tests run against the same compose db, so behavior is consistent.
**Warning signs:** Sort-order tests pass locally but fail in CI (or vice-versa).

### Pitfall 8: `expire_on_commit=True` (default) breaks SSE streams

**What goes wrong:** After `await session.commit()`, accessing any model attribute triggers a refresh — but in async-land, that refresh is a sync IO call that explodes.
**Why it happens:** SQLAlchemy default `expire_on_commit=True` is a sync-API convenience; in async, it's a footgun.
**How to avoid:** ALWAYS pass `expire_on_commit=False` to `async_sessionmaker`. Pattern 1 above sets it explicitly.
**Warning signs:** `MissingGreenlet` errors; "the greenlet spawn has not been called" exceptions after commit.

## Code Examples

### Conversation + Message + User SQLModel tables

```python
# app/db/models.py
# Source: project pattern (mirrors Phase 5 D-02 schema verbatim)

from datetime import datetime, UTC
from uuid import UUID, uuid4

from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Column, DateTime, Field, ForeignKey, SQLModel


class User(SQLModel, table=True):
    __tablename__ = "user"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    username: str = Field(unique=True, index=True, max_length=120)
    hashed_password: str = Field(max_length=200)
    disabled: bool = Field(default=False)
    created_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False,
                         server_default="now()"),
    )


class Conversation(SQLModel, table=True):
    __tablename__ = "conversation"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID = Field(
        sa_column=Column(ForeignKey("user.id", ondelete="CASCADE"),
                         nullable=False, index=True),
    )
    provider: str = Field(max_length=40)
    model: str = Field(max_length=120)
    created_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False,
                         server_default="now()"),
    )
    last_activity_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False,
                         server_default="now()"),
    )


class Message(SQLModel, table=True):
    __tablename__ = "message"
    __table_args__ = (
        # D-02 mandatory unique index for replay ordering.
        # `Index(name="message_conv_seq", unique=True)` — define inline.
        # SQLModel doesn't ship a one-liner for composite unique; use Column ux.
    )

    id: int | None = Field(default=None, primary_key=True)
    conversation_id: UUID = Field(
        sa_column=Column(ForeignKey("conversation.id", ondelete="CASCADE"),
                         nullable=False, index=True),
    )
    seq: int = Field(nullable=False)
    payload: dict = Field(sa_column=Column(JSONB, nullable=False))
    created_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False,
                         server_default="now()"),
    )

# Composite unique index — declared via SQLAlchemy `Index` since SQLModel
# Field doesn't expose a multi-column unique constraint shortcut.
from sqlalchemy import Index  # noqa: E402
Index("message_conv_seq", Message.conversation_id, Message.seq, unique=True)
```

### Settings additions

```python
# app/config.py — additions; auth_users + _DEFAULT_AUTH_USERS removed
class Settings(BaseSettings):
    ...
    # Database
    database_url: str = "postgresql+psycopg://trip_planner:trip_planner@localhost:5432/trip_planner"
    db_pool_size: int = 5
    db_pool_overflow: int = 10

    # Seed mode (dev/test only — never true in prod)
    seed_allow_non_local: bool = False
```

### Justfile additions

```makefile
# justfile — additions per D-08 / D-10 / D-11
compose-up:
    docker compose up -d --wait

compose-down:
    docker compose down

compose-down-clean:
    # Drops named volumes — equivalent of `rm -rf pgdata`.
    docker compose down -v

compose-logs:
    docker compose logs -f db

db-shell:
    docker compose exec db psql -U trip_planner -d trip_planner

migrate:
    cd backend && uv run alembic upgrade head

migrate-create MSG:
    cd backend && uv run alembic revision --autogenerate -m "{{MSG}}"

db-seed:
    cd backend && uv run python scripts/seed.py
```

### docker-compose.yml (verbatim from D-10 with Pitfall 4 note)

```yaml
# docker-compose.yml — at repo root
services:
  db:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: trip_planner
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-trip_planner}
      POSTGRES_DB: trip_planner
    ports: ["5432:5432"]    # consider 5433:5432 if conflicting with host PG (Pitfall 4)
    volumes: [pgdata:/var/lib/postgresql/data]
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U trip_planner"]
      interval: 5s
      timeout: 3s
      retries: 5

volumes:
  pgdata:
```

`docker compose up -d --wait` (compose v2.18+) blocks until all services with healthchecks report healthy — replaces hand-rolled wait loops in `just compose-up`.

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `psycopg2` sync driver | `psycopg` 3.x with native async | psycopg 3 GA 2021-10 | Use `postgresql+psycopg://` URL scheme; same SQLAlchemy types apply. |
| asyncpg-only for SQLAlchemy async | psycopg 3 + asyncpg both first-class | SQLAlchemy 2.0 GA 2023-01 | Either driver works; psycopg is often easier (libpq-based, supports server-side cursors, COPY, LISTEN/NOTIFY out of the box). |
| `pgcrypto` extension for `gen_random_uuid()` | Built-in `gen_random_uuid()` | PostgreSQL 13 GA 2020-09 | No extension needed in 16. |
| Alembic sync env.py only | `alembic init -t async` ships async template | alembic 1.7+ (2021) | Standard pattern; this repo uses it. |
| `pydantic` v1 + SQLAlchemy via two parallel classes | `sqlmodel` Pydantic v2 unified class | SQLModel 0.0.16+ (Pydantic v2 support 2024-04); Pydantic 2.12 fix in 0.0.32 (2025-02) | One class, both surfaces. |
| `LangChain` `BaseChatMessageHistory` for replay | PydanticAI `list[ModelMessage]` + `ModelMessagesTypeAdapter` | Phase 5 of this project (2026-06-03) | Phase 6 stores `ModelMessage` directly via JSONB. |

**Deprecated/outdated:**
- `psycopg2` (and `psycopg2-binary`) — use psycopg 3 (`psycopg[binary,pool]`).
- `aiopg` — superseded by psycopg 3's native async.
- `databases` (encode/databases lib) — superseded by SQLAlchemy 2.0's first-class async support.
- LangChain `BaseChatMessageHistory` — Phase 5 retired this; Phase 6 inherits the PydanticAI shape.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Postgres 16 `gen_random_uuid()` is sufficient — no need for `uuid-ossp` v5 namespacing | Don't Hand-Roll, State of the Art | LOW — recommendation already cites Postgres core docs; even if v5 were needed later, `gen_random_uuid()` is the right v1 default. |
| A2 | A 1MB payload guardrail is reasonable for `MessageStore.append` | Pattern 3, Pitfall 5 | MEDIUM — not load-tested. Planner can adjust based on observed ModelMessage sizes during execute-phase. Document the constant on Settings. |
| A3 | `pytest-postgresql` `postgresql_noproc` against compose db is faster than testcontainers | Standard Stack alternatives | LOW — both work; testcontainers' container startup is ~2-3s vs. pytest-postgresql's template-clone (~ms). |
| A4 | Single-writer-per-conversation is a safe v1 invariant | Pitfall 6 | MEDIUM — true for current single-tab UX; if a future feature lets the same user open the same conversation in two tabs, this breaks. Defensive integration test (Pitfall 6) catches the unique-violation cleanly. |
| A5 | Backend on host + db in compose collapses CORS | System Architecture Diagram, REQ-postgres-redis-compose | LOW — Vite proxy in `vite.config.ts` already proxies `/api/*` to `localhost:8000`, so backend + frontend share the browser-facing origin (`localhost:5173`). The existing `CORS_ALLOWED_ORIGINS` setting can default to the Vite origin and be removed in Phase 8 hardening. |
| A6 | `SettingsConfigDict(env_file=".env")` will pick up `DATABASE_URL` env var without code change | Settings additions | LOW — pydantic-settings convention; verified by inspection. |
| A7 | Phase 5 RunContext rewire already closes `REQ-p5-flight-client-di` (no `_flight_client` attribute) | Phase Requirements table, Pattern 1 | HIGH-CONFIDENCE — Phase 5 verification report (`05-VERIFICATION.md` truth #5) explicitly states: `search_flights._flight_client` back-door is gone; `test_search_flights_has_no_flight_client_attribute` passes. Plan-phase still needs to verify there's no residual route-plumbing concern, then either close the REQ as already-done or scope it to that residual. |
| A8 | Slopcheck OK status is sufficient legitimacy signal for these widely-used packages | Package Legitimacy Audit | LOW — packages are >5 years old, multi-million weekly downloads, official source repos. Slopcheck OK + manual sanity check on age/repo is enough. |

If A2 or A4 is wrong, planner should add an explicit checkpoint:human-verify task before execute-phase. None of these assumptions block planning.

## Open Questions

1. **Should host-port collision with Homebrew Postgres bind compose to 5433 instead of 5432?**
   - What we know: D-10 says `5432:5432`; many devs run host Postgres.
   - What's unclear: Whether the team prefers "stop your host PG" doc note vs. "we use 5433" doc note.
   - Recommendation: Default to `5433:5432` (less friction); update CONTEXT.md D-10 if planner agrees, OR leave 5432 and document the conflict in README.

2. **Where does `last_activity_at` live — `conversation` row or denormalized projection?**
   - What we know: Default per CONTEXT.md "Claude's Discretion" is column on row.
   - What's unclear: Update-on-every-message-append might cause hot-row contention if a single user has multiple concurrent conversations.
   - Recommendation: Column on `conversation` row (simplest), updated in the same transaction as `MessageStore.append`. Defer denormalization to Phase 8 if perf tells.

3. **Does `ConversationRepository` need a `bump_last_activity(conversation_id)` method, or is `update(...)` enough?**
   - What we know: D-06 lists "last_activity bump" as one of the five concerns.
   - What's unclear: Whether to ship a dedicated method or just a generic `update` that takes a partial dict.
   - Recommendation: Dedicated method — narrower API surface, easier to test, avoids "what fields are updateable" discussions.

4. **Should `seed.toml` support roles / disabled flags / additional metadata?**
   - What we know: D-08 says idempotent upsert.
   - What's unclear: Future fields (e.g., `is_admin`) might be wanted.
   - Recommendation: Ship with `username`, `password`, `disabled` (the existing `UserInDB` shape). Extending the seed format is a one-line `tomllib` change later.

5. **Frontend conversation rename — coordinate via PR or ship alongside backend?**
   - What we know: D-03 says coordinate during execute-phase.
   - What's unclear: One PR or two?
   - Recommendation: One atomic PR — backend route paths, SSE event field name, and frontend types must move together to keep `master` green. The wire-format golden file from Phase 5 is the gate (it must be regenerated to match the new field name).

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Docker | docker-compose db | ✓ | 28.5.1 | none — phase requires compose |
| `just` | justfile recipes | ✓ | 1.42.4 | direct shell commands (existing `just` already used by repo) |
| `uv` | Python deps | ✓ | 0.9.10 | none (CLAUDE.md mandates uv) |
| Python 3.13 | backend runtime | ✓ | 3.13.9 (in `backend/.venv`) | none (pyproject pins `>=3.13`) |
| `pg_isready` | compose healthcheck (run inside the postgres container, not host) | ✓ host (informational) | 17.4 (homebrew) | none — runs inside the Postgres image |
| `psql` | `just db-shell`, manual debugging | ✓ host | 17.4 | the `db-shell` recipe runs `psql` *inside* the compose container (`docker compose exec db psql ...`) so host `psql` version is informational only |
| Postgres 16 | compose `db` service | ✓ via `postgres:16-alpine` image (downloads on `compose up`) | 16.x | n/a |
| `slopcheck` | package legitimacy audit | ✓ | 0.6.1 | manual review |

**Missing dependencies with no fallback:** none.

**Missing dependencies with fallback:** none.

All required tooling is present on the dev host.

## Validation Architecture

> nyquist_validation default = enabled (config has no override).

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 8.3+ (already in deps) |
| Config file | `backend/pyproject.toml` `[tool.pytest.ini_options]` (`asyncio_mode = "auto"`, `pythonpath = ["."]`, `testpaths = ["tests"]`) |
| Quick run command | `cd backend && uv run pytest tests/unit/db tests/unit/chat -x` |
| Full suite command | `cd backend && uv run pytest` (path-discovers unit + integration + e2e) |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| REQ-postgres-redis-compose | `MessageStore.append` writes a row, `MessageStore.load` returns the same `ModelMessage` round-trip | unit | `pytest tests/unit/chat/test_postgres_message_store.py -x` | ❌ Wave 0 |
| REQ-postgres-redis-compose | `ConversationRepository.create` persists, `list_for_user` returns only user's rows | unit | `pytest tests/unit/chat/test_postgres_conversation_repo.py -x` | ❌ Wave 0 |
| REQ-postgres-redis-compose | alembic upgrade head runs against an empty db, then downgrade -1 reverses | integration | `pytest tests/integration/db/test_alembic_round_trip.py -x` | ❌ Wave 0 |
| REQ-postgres-redis-compose | `docker compose down && up` preserves data (named volume) | manual | `just compose-up && just db-seed && just compose-down && just compose-up && uv run python -c "...assert user exists..."` | manual UAT in Wave N |
| REQ-postgres-redis-compose | Concurrent appends to same conversation surface unique-violation as ErrorEvent (Pitfall 6) | integration | `pytest tests/integration/db/test_concurrent_append.py -x` | ❌ Wave 0 |
| REQ-postgres-redis-compose | Backend healthcheck flow: `pg_isready` reports healthy before backend connects | manual | `docker compose up --wait && just backend` (no error) | manual smoke |
| REQ-p5-conversation-rename | SSE wire format byte-equivalent under new `conversation_id` field name | unit | `pytest tests/unit/chat/test_stream_event_wire_compat.py -x` (regenerate golden file) | ✅ exists; needs golden update |
| REQ-p5-conversation-rename | All `/api/chat/sessions` paths return 404; new `/api/chat/conversations` paths work | integration | `pytest tests/integration/test_conversation_routes.py -x` | ❌ Wave 0 |
| REQ-p5-db-seed | `scripts/seed.py` is idempotent (run twice → same row count, hash refreshed) | integration | `pytest tests/integration/db/test_seed_idempotent.py -x` | ❌ Wave 0 |
| REQ-p5-db-seed | After seed + restart, `POST /api/auth/token` succeeds with seeded creds | integration | `pytest tests/integration/test_auth_postgres.py -x` | ❌ Wave 0 |
| REQ-p5-session-create-request-split | `POST /api/chat/conversations` accepts `{target, credentials}` shape; old shape returns 422 | integration | `pytest tests/integration/test_conversation_create_split.py -x` | ❌ Wave 0 |
| REQ-p5-flight-client-di | `search_flights` has no `_flight_client` attribute (lock from Phase 5 — confirm still passes) | unit | `pytest tests/unit/tools/test_flight_search_no_backdoor.py -x` | ✅ exists |
| REQ-p5-provider-info-split | `GET /api/llm/providers` returns `LocalProviderInfo` for ollama/lmstudio, `CloudProviderInfo` for openai/anthropic | integration | `pytest tests/integration/test_providers_endpoint.py -x` | ✅ existing — needs adjusted assertions |

### Sampling Rate

- **Per task commit:** `cd backend && uv run pytest tests/unit -x` (~10s; fast offline)
- **Per wave merge:** `cd backend && uv run pytest tests/unit tests/integration --tb=short` (requires compose db up; ~30-60s)
- **Phase gate:** Full suite green + manual compose round-trip UAT before `/gsd:verify-work`

### Wave 0 Gaps

- [ ] `tests/unit/chat/test_postgres_message_store.py` — covers REQ-postgres-redis-compose (MessageStore behavior)
- [ ] `tests/unit/chat/test_postgres_conversation_repo.py` — covers REQ-postgres-redis-compose (ConversationRepository behavior)
- [ ] `tests/integration/db/test_alembic_round_trip.py` — covers migration round-trip
- [ ] `tests/integration/db/test_concurrent_append.py` — covers Pitfall 6
- [ ] `tests/integration/db/test_seed_idempotent.py` — covers REQ-p5-db-seed idempotence
- [ ] `tests/integration/test_auth_postgres.py` — covers REQ-p5-db-seed end-to-end
- [ ] `tests/integration/test_conversation_routes.py` — covers REQ-p5-conversation-rename routes
- [ ] `tests/integration/test_conversation_create_split.py` — covers REQ-p5-session-create-request-split
- [ ] `tests/integration/db/conftest.py` — `pytest-postgresql` `postgresql_noproc` fixture pointed at compose db
- [ ] Update `tests/unit/chat/test_stream_event_wire_compat.py` golden file under `conversation_id` field
- [ ] Framework install: `cd backend && uv add --group dev pytest-postgresql`

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | yes | `pwdlib[argon2]` (already used); `PostgresUserRepository` reuses existing verify path |
| V3 Session Management | yes (auth-session, NOT chat-conversation per D-03) | JWT with `pyjwt`; existing `get_current_active_user` dep; rotated `JWT_SECRET` invalidates Phase 4.2 tokens |
| V4 Access Control | yes | Conversation rows scoped by `user_id` FK; route layer asserts ownership before delete (Phase 4.7 oracle-mitigation 404 shape) |
| V5 Input Validation | yes | Pydantic v2 validators on `ConversationTarget` / `ProviderCredentials`; existing SSRF allowlist (relocated, not rewritten) |
| V6 Cryptography | yes — never hand-roll | `pwdlib[argon2]` for passwords; `pyjwt` HS256 for tokens; `gen_random_uuid()` for IDs |

### Known Threat Patterns for Postgres + FastAPI Stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| SQL injection via dynamic queries | Tampering | SQLAlchemy ORM with parameterized binds — never string-format SQL. Seed script uses `text("INSERT … :u")` with bound params. |
| Username enumeration via response timing | Information Disclosure | Existing `_DUMMY_HASH` constant-time compare in `EnvUserRepository` — `PostgresUserRepository` MUST preserve this pattern. |
| Auth bypass via missing FK ownership check | Elevation of Privilege | `Conversation.user_id` FK + route-layer ownership check (Phase 4.7 pattern); ON DELETE CASCADE prevents orphan messages. |
| JWT replay across rotation | Repudiation | Rotate `JWT_SECRET` env var on Phase 6 deploy; existing 60-min expiry caps replay window. JWT denylist is deferred to v2. |
| Connection-string secret leak in logs | Information Disclosure | `Settings` already has `log_scrubbing.py` from Phase 4.5; ensure `database_url` (with password) is added to scrub patterns OR uses `repr()` masking. |
| Seed script run against prod | Tampering | `seed_allow_non_local: bool = False` Settings flag — abort if `database_url` host is non-localhost without flag. |
| Argon2 hash exposure on backup | Information Disclosure | DB backup encryption is an ops concern (out of phase scope) — note in ARCHITECTURE.md. Argon2 hashes are already memory-hard against offline cracking. |
| Compose db port exposed publicly | Information Disclosure / Tampering | D-10 binds `5432:5432` on host — fine for local dev, MUST be removed before any deploy. Document in README. |

## Sources

### Primary (HIGH confidence)

- [VERIFIED via `uv pip install --dry-run`] PyPI — `psycopg==3.3.4`, `sqlmodel==0.0.38`, `alembic==1.18.4`, `pytest-postgresql==8.1.0`, `sqlalchemy==2.0.50`
- [VERIFIED via `slopcheck scan`] PyPI registry legitimacy for sqlmodel, psycopg, alembic, pytest-postgresql — all OK
- [CITED: docs.sqlalchemy.org/en/20/dialects/postgresql.html] — `postgresql+psycopg://` async support
- [CITED: docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html] — `create_async_engine`, `async_sessionmaker`, AsyncEngine fork-safety
- [CITED: alembic.sqlalchemy.org/en/latest/cookbook.html#using-asyncio-with-alembic] — async env.py template
- [CITED: pydantic.dev/docs/ai/core-concepts/message-history/] — `ModelMessagesTypeAdapter` + `to_jsonable_python` round-trip
- [CITED: pydantic.dev/docs/ai/api/pydantic-ai/messages/] — full ModelMessage part-type list (TextPart, ThinkingPart, ToolCallPart, ToolReturnPart, BinaryContent, FilePart, etc.)
- [CITED: github.com/fastapi/sqlmodel sqlmodel/ext/asyncio/session.py] — SQLModel's AsyncSession subclass
- [CITED: github.com/fastapi/sqlmodel/releases] — 0.0.32 added Pydantic 2.12+ support; 0.0.38 latest
- [CITED: github.com/fastapi/full-stack-fastapi-template/blob/master/backend/app/alembic/env.py] — `target_metadata = SQLModel.metadata` pattern
- [CITED: postgresql.org/docs/16/datatype-json.html] — JSON vs JSONB; GIN indexing
- [CITED: postgresql.org/docs/16/uuid-ossp.html] — `gen_random_uuid()` in core since PG 13
- [CITED: pypi.org/project/pytest-postgresql] — `postgresql_noproc` fixture, template-clone mechanism
- [CITED: project] `.planning/phases/05-pydanticai-migration/05-CONTEXT.md` (D-08, D-11), `05-VERIFICATION.md` (truths 5–8 confirm `_flight_client` removed and ConversationStore wired)
- [CITED: project] `backend/app/chat/store.py`, `backend/app/auth/repository.py`, `backend/app/api/main.py` — existing ABC + lifespan patterns

### Secondary (MEDIUM confidence)

- [VERIFIED inference] testcontainers-python — used in many FastAPI projects but not officially listed in pytest-postgresql comparison; tradeoff comes from feature comparison.
- [INFERRED from code] 384 `session_id`/`session\b`/`SessionId` references in `backend/app`; 237 in `backend/tests` — `grep` audit on the local checkout, may include some false positives (e.g., in comments / docstrings) which the rename PR will clean up incidentally.

### Tertiary (LOW confidence)

- None.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — every package version verified against PyPI; documentation cited from official sources.
- Architecture: HIGH — patterns traceable to SQLAlchemy + Alembic + PydanticAI official docs.
- Pitfalls: HIGH — Pitfalls 1–8 are either project-specific (Phase 5 carry-forward), library-canonical (psycopg async pool, expire_on_commit), or directly observable (compose port collision).
- Compose / DX: MEDIUM — recommendations are pragmatic but not load-tested; planner can adjust pool sizes etc. during execute-phase.
- Rename inventory: MEDIUM — counts come from `grep` and may include test names / docstrings; the actual rename touches will be smaller after dedup. Refining is straightforward during planning.

**Research date:** 2026-06-03
**Valid until:** ~2026-09-03 (90 days; SQLAlchemy 2.x, psycopg 3, alembic, SQLModel are stable/mature; Pydantic v2.12 fix is locked; PydanticAI is fast-moving but Phase 5 already pinned `pydantic-ai>=0.8.1`).

---

## RESEARCH COMPLETE

**Phase:** 06 - Postgres + Docker Compose

**Confidence:** HIGH

### Key Findings

- **D-01 spike answer (HIGH):** `postgresql+psycopg://` works natively with SQLAlchemy 2.0 + SQLModel 0.0.38. Use `from sqlmodel.ext.asyncio.session import AsyncSession`. No glue needed; `asyncpg` fallback unnecessary.
- **alembic + SQLModel + async (HIGH):** `alembic init -t async backend/migrations`; `target_metadata = SQLModel.metadata` after importing every table module. Cookbook async env.py pattern is canonical.
- **PydanticAI ModelMessage JSONB (HIGH):** `to_jsonable_python(result.all_messages())` → JSONB column → `ModelMessagesTypeAdapter.validate_python(rows)` round-trips cleanly. Phase 5 verified OQ-05. Watch for BinaryContent/FilePart bloat (out of v1 scope).
- **Test DB strategy (HIGH):** `pytest-postgresql 8.1.0` `postgresql_noproc` fixture against compose `db` is the recommended path. testcontainers fallback documented.
- **Idempotent seed (HIGH):** `tomllib` (stdlib) + `pwdlib argon2` + `INSERT … ON CONFLICT DO UPDATE`. Pattern shown.
- **JWT rotation (HIGH):** No code change needed — env-var swap of `JWT_SECRET` in the new `.env` shipped with the phase invalidates Phase 4.2 tokens automatically.
- **Compose healthcheck (HIGH):** `pg_isready -U trip_planner` inside container + `docker compose up -d --wait`. Documented Pitfall 4 (port 5432 collision with host PG); recommendation to bind 5433:5432 (open question OQ-1).
- **Codebase rename (MEDIUM):** ~384 backend + ~237 test + ~30 frontend files touch `session_id`. Wire-format golden file from Phase 5 must be regenerated to match `conversation_id`. One atomic PR.
- **`REQ-p5-flight-client-di` likely already closed (HIGH):** Phase 5 verification truth #5 confirms `_flight_client` back-door removed; Phase 6 plan should verify and either close as already-done or scope to residual route plumbing.
- **Architectural responsibility map:** All Phase 6 capabilities live on Backend + Database tiers; rename is the only frontend-touching capability.

### File Created

`/Users/axel/code/trip_planner/.planning/phases/06-postgres-redis-docker-compose/06-RESEARCH.md`

### Confidence Assessment

| Area | Level | Reason |
|------|-------|--------|
| Standard Stack | HIGH | All versions verified via uv resolution + official docs cited |
| Architecture | HIGH | SQLAlchemy + alembic patterns are canonical and well-documented |
| Pitfalls | HIGH | Mix of library-canonical (Pitfalls 1, 3, 8) and project-specific (Pitfalls 4, 6) — all traceable |
| Test Strategy | HIGH | pytest-postgresql official; tradeoff vs testcontainers explicit |
| Rename Inventory | MEDIUM | grep counts include false positives; planner refines during planning |

### Open Questions

1. Compose port: 5432 (collision risk) vs 5433 (safer) — recommend 5433.
2. `last_activity_at` placement: column on row (default) vs denormalized projection — recommend column.
3. `ConversationRepository.bump_last_activity` dedicated method vs generic `update` — recommend dedicated.
4. `seed.toml` schema fields beyond username/password/disabled — defer until needed.
5. Frontend rename PR coordination: one atomic PR vs split — recommend one atomic.

### Ready for Planning

Research complete. Planner can now create PLAN.md files. The phase has near-zero novel surface area at the library level; the bulk of the planning work is sequencing (Wave 0 spike → Wave 1 schema + alembic → Wave 2 stores → Wave 3 routes + rename → Wave 4 frontend coordination → Wave N seed + UAT) and the codebase-wide rename refactor.
