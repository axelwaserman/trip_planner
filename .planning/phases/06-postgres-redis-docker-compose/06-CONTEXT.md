# Phase 6: Postgres + Docker Compose - Context

**Gathered:** 2026-06-03
**Status:** Ready for planning

> Note: Phase name in ROADMAP/STATE remains `postgres-redis-docker-compose` for ID stability. Redis was scoped out during discussion (D-04). Compose ships with Postgres only.

<domain>
## Phase Boundary

Re-platform persistence from in-process dicts to Postgres. Ship `docker-compose.yml` so the stack runs locally with one command. Replace `EnvUserRepository` with a Postgres-backed implementation. Replace the in-memory `ConversationStore` with a Postgres event-log implementation, fronted by a stable ABC seam so a Redis cache can be added later without rewrites.

In scope:
- Postgres 16 service in `docker-compose.yml`
- SQLModel + alembic migrations from day 1
- `MessageStore` ABC with `InMemory` + `Postgres` implementations
- `ConversationRepository` ABC with `InMemory` + `Postgres` implementations
- `PostgresUserRepository` replacing `EnvUserRepository`
- `just db-seed` recipe + `scripts/seed.py` + `seed.toml`
- Codebase-wide rename `session` → `conversation`

Out of scope (deferred):
- Redis (any role)
- Multi-replica backend deployment
- Rate limiting (per ADR-009)
- Frontend changes beyond what conversation rename requires

</domain>

<decisions>
## Implementation Decisions

### DB driver + ORM
- **D-01:** Pre-phase spike (Wave 0, must complete before main planning) verifies `postgresql+psycopg://` async driver + SQLModel + SQLAlchemy 2.0 compatibility against the ChatService event-log shape. Fallback to `asyncpg` only if `psycopg[binary,pool]` async support has gaps. Spike output: short ADR amendment + working async session factory in `app/db/session.py`.
- **D-11:** alembic from day 1. Config at `backend/alembic.ini`, migrations at `backend/migrations/`. `env.py` reads `Settings.database_url` and imports SQLModel metadata for `--autogenerate`. Justfile recipes:
  - `just migrate` → `cd backend && uv run alembic upgrade head`
  - `just migrate-create MSG` → `uv run alembic revision --autogenerate -m "$MSG"`
- Migrations execute on host via `uv` env. Compose only runs the DB container.

### Conversation message storage
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
  Rationale: matches LangGraph / OpenAI Agents SDK durable-state pattern. Each `ModelMessage` from PydanticAI serializes to one row via `ModelMessagesTypeAdapter`. Replay = `SELECT payload FROM message WHERE conversation_id = $1 ORDER BY seq`. Future agentic-state generation (snapshots, branching, replay-from-step) layered on top of the log.
- **D-05:** `MessageStore` ABC seam:
  ```python
  class MessageStore(ABC):
      @abstractmethod
      async def append(self, conversation_id: UUID, payload: dict) -> None: ...
      @abstractmethod
      async def load(self, conversation_id: UUID) -> list[ModelMessage]: ...
      @abstractmethod
      async def delete(self, conversation_id: UUID) -> None: ...
  ```
  Phase 6 ships `InMemoryMessageStore` (dict-of-lists, used in unit tests + dev fallback) and `PostgresMessageStore` (event-log writer). Future `RedisMessageStore` and `HybridMessageStore` (Redis hot-path + Postgres durable) slot in via the same ABC without ChatService changes.
- **D-06:** Split conversation persistence into two ABCs:
  - `MessageStore` — events (append/load/delete)
  - `ConversationRepository` — meta CRUD (create, rename, list_for_user, last_activity bump, delete)
  Both ship `InMemory` + `Postgres` implementations. Wired via `app.state.message_store` and `app.state.conversation_repo` in lifespan.

### Naming
- **D-03:** Rename `session` → `conversation` codebase-wide as part of Phase 6. Closes carry-forward `REQ-p5-conversation-rename`. Touches:
  - `ChatService._sessions` → `_conversations` (or removed entirely once dicts move to repos)
  - `SessionId` type alias → `ConversationId`
  - `/api/chat/sessions` routes → `/api/chat/conversations`
  - `session_id` query/body params → `conversation_id`
  - Frontend `sessionId` state, SSE event payloads, telemetry keys
  Migration is mechanical but cross-cutting. Coordinate with frontend during execute-phase.

### Redis scope
- **D-04:** No Redis in Phase 6. compose ships `db` service only. v1 documented as single-replica; multi-replica + Redis cache layer deferred to a later phase. Rationale: Postgres alone covers durability and `_metadata` / `_last_activity` writes; ABC seams (D-05, D-06) keep the door open for `RedisMessageStore` / `RedisConversationRepository` without ChatService rewrites.
- Provider models cache and active-stream tracking remain in-process for v1 (already are).

### Auth + user store
- **D-07:** `EnvUserRepository` deleted in Phase 6. `AUTH_USERS` env removed from `Settings`. `PostgresUserRepository` is the sole implementation. JWT secret + token rotation handling unchanged.
- **D-08:** Dev/test bootstrap via `just db-seed`. Implementation:
  - `backend/scripts/seed.py` — idempotent upsert from `seed.toml`
  - `seed.toml` is gitignored; `seed.toml.example` committed with placeholder creds
  - Argon2 hash via `pwdlib` happens at seed time; plaintext passwords never persisted
  - Run order on fresh checkout: `just compose-up && just migrate && just db-seed`
- **D-09:** No password migration. Reseed clean — the project has no production users yet, so the EnvUserRepository drop is a clean break. `seed.toml.example` ships dev creds.

### Compose shape + DX
- **D-10:** docker-compose v1 services:
  ```
  services:
    db:
      image: postgres:16-alpine
      environment:
        POSTGRES_USER: trip_planner
        POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-trip_planner}
        POSTGRES_DB: trip_planner
      ports: ["5432:5432"]
      volumes: [pgdata:/var/lib/postgresql/data]
      healthcheck:
        test: ["CMD-SHELL", "pg_isready -U trip_planner"]
        interval: 5s
        timeout: 3s
        retries: 5
  volumes:
    pgdata:
  ```
  Backend + frontend run on host (`just backend`, `just frontend`). New justfile recipes: `just compose-up`, `just compose-down`, `just compose-logs`, `just db-shell`.

### Carry-forward REQs from Phase 5
Phase 6 must close (per ROADMAP):
- `REQ-p5-conversation-rename` — handled in D-03
- `REQ-p5-db-seed` — handled in D-08
- `REQ-p5-session-create-request-split` — split `POST /api/chat/conversations` request body from internal create-conversation arg shape; Pydantic request model only
- `REQ-p5-flight-client-di` — promote `search_flights._flight_client` injection to a proper FastAPI dep (`app.state.flight_client`) so test overrides don't reach into module attributes
- `REQ-p5-provider-info-split` — split `/api/llm/providers` response from internal `ProviderInfo` model; ship a `ProviderInfoResponse` Pydantic schema

### Claude's Discretion
- Exact SQLModel class layout (e.g., split table classes vs. unified) within ABC contracts
- Index choice beyond the mandatory `message(conversation_id, seq)` unique index
- alembic env.py wiring details (sync vs async run_migrations_online)
- Justfile recipe naming beyond the names listed in D-08/D-10/D-11
- `seed.toml` schema (TOML structure under those tables)
- Exact `ConversationRepository` method names beyond the listed five concerns
- pgcrypto vs Python-side UUID generation for primary keys
- Whether `last_activity_at` lives on `conversation` row or in a denormalized projection (default: column on row)

</decisions>

<specifics>
## Specific Ideas

- "In the future we want to generate agent state dynamically, similar to what all agentic platforms do." → drove D-02 (event log) over a single-blob JSONB column. Snapshots / branching / replay-from-step layer on top of the log later.
- "Implement an ABC for message storage with postgres and in-memory implementations so if we want to add Redis later it makes it easier." → drove D-05/D-06 ABC split.
- ADR-006 (Postgres) listed as Pending in `PROJECT.md` but no standalone ADR file exists. Phase 6 must author `.planning/adrs/ADR-006-postgres.md` capturing: driver choice (D-01 spike outcome), event-log schema (D-02), ABC seams (D-05/D-06), Redis deferral rationale (D-04).

</specifics>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project-level
- `.planning/PROJECT.md` — ADR table, locked decisions, project guardrails
- `.planning/ROADMAP.md` — Phase 6 scope, carry-forward REQs, sequencing
- `.planning/REQUIREMENTS.md` — `REQ-postgres-redis-compose` + `REQ-p5-*` carry-forward IDs
- `.planning/STATE.md` — phase status, current focus
- `CLAUDE.md` — repo-wide constraints (async I/O, pyreqwest only, ABC over Protocol, StrEnum for taxonomies, Settings for tunables)

### Phase 5 (predecessor)
- `.planning/phases/05-pydanticai-migration/05-CONTEXT.md` — D-08 ConversationStore ABC, D-11 list[ModelMessage] storage shape, OQ-05 ModelMessagesTypeAdapter round-trip findings
- `.planning/phases/05-pydanticai-migration/05-VERIFICATION.md` — what shipped, what was deferred
- `backend/app/chat/store.py` — current `ConversationStore` ABC (the seam Phase 6 extends/splits)
- `backend/app/chat/service.py` — `ChatService` lifecycle, `agent.iter()` loop, where stores plug in

### Architecture + ADRs
- `ARCHITECTURE.md` — Data Model Pattern, Abstract Client Pattern, Functional Service Pattern, Dependency Injection Pattern
- `.planning/adrs/ADR-007-pydantic-ai.md` — agent runtime contract Phase 6 must preserve
- `.planning/adrs/ADR-001-langchain.md` (Superseded, but explains migration history)
- `.planning/adrs/ADR-006-postgres.md` — **does not exist yet**; Phase 6 must author this
- ADR-008 (pyreqwest only for HTTP) — referenced in CLAUDE.md, no separate file

### Existing implementations to extend
- `backend/app/auth/repository.py` — `UserRepository` ABC + `EnvUserRepository`. Phase 6 adds `PostgresUserRepository`, deletes `EnvUserRepository` per D-07.
- `backend/app/api/main.py` — lifespan singletons via `app.state`. Phase 6 adds `app.state.db_engine`, `app.state.message_store`, `app.state.conversation_repo`.
- `backend/app/config.py` — `Settings`. Phase 6 adds `database_url`, removes `auth_users`.
- `backend/pyproject.toml` — adds `sqlmodel`, `psycopg[binary,pool]`, `alembic`. (No `redis` per D-04.)
- `justfile` — adds `compose-up`, `compose-down`, `compose-logs`, `db-shell`, `migrate`, `migrate-create`, `db-seed`.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `ConversationStore` ABC at `backend/app/chat/store.py` — direct ancestor of D-06 split. Methods (`append`, `load`, `delete`, `list_for_user`) inform `MessageStore` + `ConversationRepository` shapes.
- `UserRepository` ABC at `backend/app/auth/repository.py` — pattern for `PostgresUserRepository` (D-07). `EnvUserRepository` shows how `pwdlib` Argon2 verification is wired; reuse the verification path, swap the storage backend.
- `app.state` singleton pattern in `api/main.py::lifespan` — Phase 6 extends with DB engine + new repos; same pattern, no new wiring concept.
- `MockLLM` and `tests/fixtures/` — integration tests get `InMemoryMessageStore` + `InMemoryConversationRepository` swapped in via dependency overrides.

### Established Patterns
- ABC over Protocol (CLAUDE.md): all new interfaces (`MessageStore`, `ConversationRepository`) MUST be `class Foo(ABC)`.
- StrEnum for cross-module taxonomies (CLAUDE.md): if Phase 6 introduces wire-level codes (e.g., `MessageRole`, `ConversationStatus`), use StrEnum, not `Literal[...]` unions.
- Settings for tunables (CLAUDE.md): `database_url`, pool size, statement timeout → `Settings`, not module constants.
- Async-only I/O (CLAUDE.md): all repository methods are `async def`. SQLAlchemy `AsyncSession`, never sync.
- pyreqwest for outbound HTTP (ADR-008): does not affect Phase 6 directly — Postgres uses `psycopg`, not HTTP.
- Path-based test selection (CLAUDE.md): unit tests use `InMemory*` impls; integration tests get `Postgres*` impls against a real test DB started via compose; e2e remains symbolic gate.

### Integration Points
- `ChatService.__init__` currently accepts a `ConversationStore`. Phase 6 changes its signature to accept `MessageStore` + `ConversationRepository`. Touch points: `lifespan`, `get_chat_service` dep, all integration test fixtures.
- `auth/routes.py::login` and `get_current_active_user` — repo swap is transparent; route code does not change.
- `chat/routes.py::chat_stream` — receives `conversation_id` (renamed from `session_id` per D-03). Request/response Pydantic models updated, SSE event payloads updated, frontend follows.
- `tests/integration/conftest.py` — needs a `postgres_container` or `pytest-postgresql` fixture for repo-level tests. Decision deferred to planner; spike-time finding may inform.

</code_context>

<deferred>
## Deferred Ideas

- **Redis any-role** — deferred to a post-Phase-6 phase. Triggers: multi-replica backend deploy, hot-path read latency on conversation meta, active-stream tracking across pods. ABC seams (D-05/D-06) make this a non-disruptive add.
- **Agent state snapshots / branching / replay-from-step** — D-02 event log is the substrate. Snapshot table + branch pointers layer on top. Pencilled in for the agentic-platform-features phase, not Phase 6.
- **Multi-replica backend** — single-replica documented as v1 limit (D-04). Coordinated state (Redis or Postgres advisory locks) needed before scaling.
- **Rate limiting** — already deferred per ADR-009.
- **Frontend conversation history sidebar** — D-03 rename touches frontend, but new UX (history list, conversation switcher) is out of Phase 6 scope.
- **`pytest-postgresql` vs testcontainers** decision — planner picks during plan-phase based on spike outcome.
- **Adminer / pgAdmin in compose** — Claude's discretion; not required for Phase 6.

</deferred>

---

*Phase: 06-postgres-redis-docker-compose*
*Context gathered: 2026-06-03*
