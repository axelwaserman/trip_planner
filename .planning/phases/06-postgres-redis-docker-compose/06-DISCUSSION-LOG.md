# Phase 6: Postgres + Docker Compose - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in `06-CONTEXT.md` — this log preserves the alternatives considered.

**Date:** 2026-06-03
**Phase:** 06-postgres-redis-docker-compose
**Areas discussed:** DB driver + schema, Redis role + ephemeral state, User migration + seeding, Compose shape + DX

---

## Workflow kickoff

| Option | Description | Selected |
|--------|-------------|----------|
| `phase/06-postgres-redis-compose` | Branch name aligned with phase scope | ✓ |

| Option | Description | Selected |
|--------|-------------|----------|
| `/gsd:discuss-phase` | Explore + clarify before planning | ✓ |
| `/gsd:plan-phase` | Skip discussion, go straight to plan | |
| Manual scaffold | Hand-create context | |

**User's choice:** `phase/06-postgres-redis-compose` + `/gsd:discuss-phase`.

---

## Area 1 — DB driver + schema

### Q1: psycopg vs asyncpg + SQLModel compatibility

| Option | Description | Selected |
|--------|-------------|----------|
| psycopg + SQLModel (pre-phase spike) | Verify `postgresql+psycopg://` async + SQLModel works against event-log shape before planning | ✓ |
| asyncpg + SQLModel | Use asyncpg directly; lighter but less SQLAlchemy-canonical | |
| psycopg + raw SQLAlchemy Core | Skip SQLModel, hand-roll mappers | |
| asyncpg + Tortoise/Piccolo | Different ORM stack | |

**User's choice:** psycopg + SQLModel (pre-phase spike).
**Notes:** Locked as **D-01**. Spike happens in Wave 0, blocks main planning.

### Q2: ModelMessage storage shape (initial framing — single blob vs normalized)

| Option | Description | Selected |
|--------|-------------|----------|
| Single JSONB blob | One row per conversation; `messages JSONB` column holds full list | redirected |
| Normalized rows | Foreign-keyed rows per message | redirected |

**User redirect:** *"In the future we want to generate agent state dynamically, similar to what all agentic platforms do. Taking that into account, what are the 2-3 approaches you'd recommend?"*

### Q2 (re-framed): Agentic-state-aware storage

| Option | Description | Selected |
|--------|-------------|----------|
| A — Single JSONB blob | Simple; rewrites whole list on every append | |
| B — Append-only event log (LangGraph / OpenAI Agents SDK pattern) | One row per ModelMessage; replay by ORDER BY seq; substrate for snapshots, branching, replay-from-step | ✓ |
| C — Event log + materialized state snapshot | B plus periodic snapshot rows for fast reads | |

**User's choice:** B — Append-only event log.
**Notes:** Locked as **D-02**. Schema specified in CONTEXT. C-style snapshots deferred to a future agentic-platform-features phase.

### Q3: `session` → `conversation` rename

| Option | Description | Selected |
|--------|-------------|----------|
| Yes — rename in Phase 6 | Closes carry-forward `REQ-p5-conversation-rename`; touches backend + frontend + SSE payloads | ✓ |
| Defer to later phase | Keep `session` naming for now | |

**User's choice:** Yes.
**Notes:** Locked as **D-03**.

---

## Area 2 — Redis role + ephemeral state

### Q1 (initial): What goes in Redis?

| Option | Description | Selected |
|--------|-------------|----------|
| Active-stream tracking | Cross-pod awareness of in-flight SSE streams | |
| Provider models cache | TTL cache of `/api/llm/providers` response | |
| Conversation `_metadata` / `_last_activity` | Hot meta state (was leaning toward) | (later dropped) |
| Agent instances | Cache PydanticAI Agent objects across requests | |

### Q2 (initial): Backend replicas v1

| Option | Description | Selected |
|--------|-------------|----------|
| Single replica recommended | Simpler, defer Redis | |
| Multi-replica from v1 | Justifies Redis from day 1 | |

**User clarification request:** asked to clarify before answering. Trigger phrase: *"explain pros and cons and propose 2-3 alternatives"*.

### Q1 (re-framed): Redis for `_metadata` / `_last_activity`?

Three alternatives presented:
1. Redis-backed `_metadata` / `_last_activity`
2. Postgres-only (one source of truth, +1ms write latency, no degraded mode)
3. In-memory + Postgres write-through

### Q1 (final): Redis scope

**User's directive:** *"Dump Redis for now but make sure to implement an ABC for message storage with postgres and in-memory implementations so if we want to add Redis later it makes it easier."*

| Option | Description | Selected |
|--------|-------------|----------|
| Redis in compose v1 | Ship Redis service for any role from day 1 | |
| Postgres-only + ABC seam | No Redis. `MessageStore` + `ConversationRepository` ABCs with InMemory + Postgres impls; Redis slot-in later | ✓ |

**User's choice:** Postgres-only + ABC seam.
**Notes:** Locked as **D-04** (no Redis), **D-05** (`MessageStore` ABC + InMemory + Postgres impls), **D-06** (split `MessageStore` events vs `ConversationRepository` meta).

---

## Area 3 — User migration + seeding

### Q1: `EnvUserRepository` fate

| Option | Description | Selected |
|--------|-------------|----------|
| Drop completely | Remove class + `AUTH_USERS` env. Postgres sole user store | ✓ |
| Keep as fallback | Postgres primary, env fallback if DB unreachable | |
| Keep for tests only | Postgres in dev/prod, env in unit tests | |
| Migrate then delete | Ship both, one-shot migration, delete in Phase 6.1 | |

**User's choice:** Drop completely.
**Notes:** Locked as **D-07**. `AUTH_USERS` removed from `Settings`.

### Q2: Dev seed flow

| Option | Description | Selected |
|--------|-------------|----------|
| `just db-seed` recipe | Standalone `scripts/seed.py`, idempotent, reads `seed.toml` | ✓ |
| Alembic data migration | Seed lives in alembic revision file | |
| Auto-seed on backend startup | Lifespan checks empty users table, seeds | |
| compose entrypoint script | `init.sql` runs in `db` container | |

**User's choice:** `just db-seed` recipe.
**Notes:** Locked as **D-08**. `seed.toml.example` committed; `seed.toml` gitignored. Argon2 hash at seed time.

### Q3: Password handling at migration

| Option | Description | Selected |
|--------|-------------|----------|
| No migration — reseed | Clean break (no real users yet) | ✓ |
| One-shot migration script | Read `AUTH_USERS` env, write to Postgres | |
| Rehash on first login | Lazy migration via login path | |
| Force password reset | Email-driven reset (no email infra) | |

**User's choice:** No migration — reseed.
**Notes:** Locked as **D-09**.

---

## Area 4 — Compose shape + DX

### Q1: docker-compose service set

| Option | Description | Selected |
|--------|-------------|----------|
| db only + backend on host | compose ships only Postgres; backend + frontend run on host | ✓ |
| db + backend in compose | Backend containerized with bind-mount hot-reload | |
| db + backend + frontend full stack | Everything in compose | |
| db + backend + adminer | Adds web DB UI | |

**User's choice:** db only + backend on host.
**Notes:** Locked as **D-10**. `pg_isready` healthcheck, named `pgdata` volume, port 5432 published.

### Q2 (initial): Migration UX

**User clarification request:** *"Why are we using alembic?"*

Pros/cons explained:
1. SQLModel `create_all()` — zero config, no migrations, painful first schema change
2. alembic — versioned, autogenerate, rollback, industry standard, +1 file +1 dir
3. Manual SQL files — reinventing alembic poorly

**User's directive:** *"Go for alembic"*. Locked as ORM-migration choice.

### Q2 (re-asked): Where does `just migrate` run?

| Option | Description | Selected |
|--------|-------------|----------|
| Host — `uv run alembic upgrade head` | Compose only provides DB; migrations on host | ✓ |
| In compose via one-shot service | `docker compose run --rm migrator alembic upgrade head` | |
| Auto-run on backend startup | Lifespan calls `upgrade head` before serving | |
| Both — host dev, compose CI | Two paths | |

**User's choice:** Host.
**Notes:** Locked as **D-11**. `just migrate` + `just migrate-create MSG`.

---

## Claude's Discretion

The following are explicitly delegated to Claude during planning/execution:

- Exact SQLModel class layout within ABC contracts (D-05/D-06)
- Indexes beyond mandatory `message(conversation_id, seq)` unique
- alembic `env.py` wiring (sync vs async run_migrations_online)
- Justfile recipe naming beyond names listed in D-08/D-10/D-11
- `seed.toml` schema (TOML structure under tables)
- Exact `ConversationRepository` method names
- pgcrypto vs Python-side UUID generation for primary keys
- Whether `last_activity_at` lives on `conversation` row or in a denormalized projection (default: column)

## Deferred Ideas

- **Redis any-role** — post-Phase-6. ABC seams keep this non-disruptive.
- **Agent state snapshots / branching / replay-from-step** — built on D-02 event log; agentic-platform-features phase.
- **Multi-replica backend** — single-replica documented as v1 limit.
- **Rate limiting** — already deferred per ADR-009.
- **Frontend conversation history sidebar** — out of Phase 6 scope.
- **`pytest-postgresql` vs testcontainers** — planner picks during plan-phase.
- **Adminer / pgAdmin in compose** — discretion; not required.

---

*Phase: 06-postgres-redis-docker-compose*
*Discussion log generated: 2026-06-03*
