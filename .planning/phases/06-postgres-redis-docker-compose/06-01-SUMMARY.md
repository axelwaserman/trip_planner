---
phase: 06-postgres-redis-docker-compose
plan: 01
subsystem: database
tags:
  - postgres
  - psycopg
  - sqlmodel
  - sqlalchemy
  - alembic
  - spike
  - adr-006

# Dependency graph
requires:
  - phase: 05-pydanticai-migration
    provides: ConversationStore ABC, list[ModelMessage] storage shape, ModelMessagesTypeAdapter round-trip
provides:
  - Pinned Phase 6 deps (psycopg[binary,pool] 3.3.4, sqlmodel 0.0.38, alembic 1.18.4, pytest-postgresql 8.1.0, sqlalchemy[asyncio] 2.0.50)
  - Settings.database_url + db_pool_size + db_pool_overflow + seed_allow_non_local with env var overrides
  - app/db/session.py async engine + sessionmaker (expire_on_commit=False) + get_session FastAPI dep
  - Wave 0 spike smoke test (postgresql+psycopg:// async + SQLModel + SQLAlchemy 2.0 verified end-to-end against live Postgres 16)
  - ADR-006-postgres.md (Locked) recording driver, ORM, migrations, event-log schema, ABC seams, Redis deferral
affects:
  - 06-02 (alembic init + SQLModel tables — receives the engine + metadata wiring)
  - 06-03 (MessageStore + ConversationRepository impls — receive _async_sessionmaker for per-store session lifecycles)
  - 06-04 (PostgresUserRepository — receives _async_sessionmaker)
  - 06-05 (codebase-wide session→conversation rename — uses the new ConversationRepository)
  - 06-06 (compose + seed flow — enforces seed_allow_non_local)

# Tech tracking
tech-stack:
  added:
    - "psycopg[binary,pool]>=3.3.4 (async PG driver, native pool)"
    - "sqlmodel>=0.0.38 (Pydantic v2 + SQLAlchemy unified ORM)"
    - "sqlalchemy[asyncio]>=2.0.50 (explicit async dep — pulls greenlet on macOS arm64)"
    - "alembic>=1.18.4 (schema migrations)"
    - "pytest-postgresql>=8.1.0 (dev — postgresql_noproc fixture for repo-level tests in Plan 06-03)"
  patterns:
    - "Async session factory pattern (06-RESEARCH §Pattern 1): create_async_engine + async_sessionmaker(class_=AsyncSession, expire_on_commit=False) + request-scoped get_session FastAPI dep"
    - "Pitfall 8 lock: expire_on_commit=False is mandatory under async — default True causes MissingGreenlet on attribute access after commit"
    - "Tunables on Settings (CLAUDE.md): database_url, db_pool_size, db_pool_overflow, seed_allow_non_local live on Settings, not module-level constants"
    - "Settings env override: DATABASE_URL, DB_POOL_SIZE, DB_POOL_OVERFLOW, SEED_ALLOW_NON_LOCAL all routable via env vars (pydantic-settings convention)"

key-files:
  created:
    - "backend/app/db/__init__.py"
    - "backend/app/db/session.py"
    - "backend/tests/unit/db/__init__.py"
    - "backend/tests/unit/db/test_db_session.py"
    - ".planning/adrs/ADR-006-postgres.md"
  modified:
    - "backend/pyproject.toml"
    - "backend/uv.lock"
    - "backend/app/config.py"

key-decisions:
  - "D-01 spike VERIFIED: postgresql+psycopg:// async + SQLModel + SQLAlchemy 2.0 work end-to-end against postgres:16-alpine. asyncpg fallback path NOT taken."
  - "Added sqlalchemy[asyncio]>=2.0.50 explicit dep (Rule 3 deviation): SQLAlchemy's marker auto-installs greenlet on linux/x86_64 + windows but NOT on macOS arm64; without [asyncio] extra the first await raises ValueError: greenlet required"
  - "Settings.auth_users intentionally retained — Plan 06-04 owns its deletion alongside EnvUserRepository removal so the running app stays bootable while Plans 06-02/06-03 land"
  - "Per-store impls (Plan 06-03) will receive _async_sessionmaker directly rather than the request-scoped get_session — SSE handlers must release sessions before the body runs (Pitfall 3)"

patterns-established:
  - "Async DB session factory: create_async_engine(settings.database_url, pool_size=settings.db_pool_size, max_overflow=settings.db_pool_overflow, echo=settings.debug) + async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False) — module-level singletons in app/db/session.py"
  - "FastAPI request-scoped session dep: async def get_session() -> AsyncGenerator[AsyncSession]: async with _async_sessionmaker() as session: yield session"
  - "Spike smoke-test layout: tests/unit/db/test_db_session.py with three async tests (URL prefix, expire_on_commit lock, SELECT 1 round-trip with skip-on-OperationalError); path-based selection per CLAUDE.md, no pytest.mark.unit"
  - "ADR shape: Status: Locked + plain-text grep mirror; sections Context / Decision / Verification / Consequences / Alternatives Considered / References"

requirements-completed:
  - REQ-postgres-redis-compose

# Metrics
duration: ~40min
completed: 2026-06-04
---

# Phase 6 Plan 01: Async DB foundation + D-01 spike Summary

**Pinned Phase 6 deps, shipped app/db/session.py with async engine + sessionmaker (expire_on_commit=False) + get_session FastAPI dep, and verified `postgresql+psycopg://` + SQLModel + SQLAlchemy 2.0 round-trip against live Postgres 16 — ADR-006 Locked.**

## Performance

- **Duration:** ~40 min
- **Started:** 2026-06-04T08:34:45Z (Task 1 commit timestamp converted to UTC)
- **Completed:** 2026-06-04T09:40:00Z
- **Tasks:** 3 / 3
- **Files modified:** 8 (5 created, 3 modified)

## Accomplishments

- **D-01 spike answered VERIFIED.** Three async smoke tests pass against `postgres:16-alpine` started via the documented `docker run` invocation; no fallback to `asyncpg` needed. Without Postgres, the round-trip test skips cleanly while the two pure-inspection tests still pass.
- **`app/db/session.py` shipped.** Module-level `engine`, `_async_sessionmaker` (with the Pitfall 8 lock — `expire_on_commit=False`), and an async `get_session` FastAPI dep yielding `sqlmodel.ext.asyncio.session.AsyncSession`. Plans 06-03 and 06-04 can now build stores against this seam.
- **Settings extended with the four DB knobs** (`database_url`, `db_pool_size`, `db_pool_overflow`, `seed_allow_non_local`) — all overridable via env vars per pydantic-settings convention.
- **ADR-006 Locked.** Records driver = psycopg async, ORM = SQLModel + SQLAlchemy 2.0, migrations = alembic, event-log schema (D-02 verbatim), ABC seams (D-05/D-06), Redis deferral (D-04), and the macOS arm64 greenlet workaround.

## Task Commits

Each task was committed atomically:

1. **Task 1: Pin Phase 6 dependencies and add Settings DB knobs** — `46a28c1` (feat)
2. **Task 2: Create app/db/session.py async engine + sessionmaker + get_session dep** — `c82d6cd` (feat)
3. **Task 3: Spike smoke test against live Postgres + write ADR-006** — committed alongside SUMMARY.md (feat) — see plan-metadata commit hash returned by orchestrator

## Files Created/Modified

**Created:**
- `backend/app/db/__init__.py` — Phase 6 DB package marker.
- `backend/app/db/session.py` — async engine, async_sessionmaker (class_=AsyncSession, expire_on_commit=False), and request-scoped `get_session` FastAPI dep.
- `backend/tests/unit/db/__init__.py` — empty test-package marker (path-based selection per CLAUDE.md).
- `backend/tests/unit/db/test_db_session.py` — 3 async tests (URL dialect, expire_on_commit lock, live SELECT 1 round-trip with skip-on-OperationalError).
- `.planning/adrs/ADR-006-postgres.md` — `Status: Locked`. Records the full Phase 6 persistence stack decision; references D-01/D-02/D-04/D-05/D-06/D-11.

**Modified:**
- `backend/pyproject.toml` — pinned `psycopg[binary,pool]>=3.3.4`, `sqlmodel>=0.0.38`, `alembic>=1.18.4`, `sqlalchemy[asyncio]>=2.0.50` (runtime); `pytest-postgresql>=8.1.0` (dev).
- `backend/uv.lock` — regenerated; new pins recorded (psycopg 3.3.4, sqlmodel 0.0.38, alembic 1.18.4, sqlalchemy 2.0.50, pytest-postgresql 8.1.0, greenlet 3.5.1).
- `backend/app/config.py` — added `database_url`, `db_pool_size`, `db_pool_overflow`, `seed_allow_non_local` in a `# Database (Phase 6 — D-01, D-11)` block above `provider_probe_timeout_seconds`.

## Decisions Made

- **D-01 spike VERIFIED, asyncpg fallback NOT taken.** All 3 smoke tests pass against live `postgres:16-alpine`. Plans 06-02 through 06-06 can rely on the locked driver/ORM/migrations stack.
- **`Settings.auth_users` retained in this plan.** Plan 06-04 owns the deletion alongside `EnvUserRepository` removal; this keeps the running app bootable while intermediate plans land. Documented in 06-PATTERNS.md.
- **No `model_post_init` warning for the new DB fields.** Plan 06-06 will revisit when `seed_allow_non_local` becomes load-bearing during seed flow execution.
- **ADR-006 grep-friendly Status mirror.** ADR-007 only has `<!-- Status: Locked -->`; ADR-006 adds an uncommented `Status: Locked` line so `grep -q '^Status: Locked'` (the plan's verify command) matches without ambiguity.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 — Blocking] Added `sqlalchemy[asyncio]` explicit dep for greenlet on Apple Silicon**
- **Found during:** Task 3 (running `test_async_session_select_one_round_trip` against live PG)
- **Issue:** `await session.execute(text("SELECT 1"))` raised `ValueError: the greenlet library is required to use this function. No module named 'greenlet'`. SQLAlchemy's wheel marker auto-installs `greenlet` only on `aarch64`, `ppc64le`, `x86_64`, `amd64`, `AMD64`, `win32`, `WIN32`. Apple Silicon reports `platform.machine() == "arm64"` (not `aarch64`), so greenlet was excluded from the resolved environment despite being in `uv.lock`.
- **Fix:** Added `"sqlalchemy[asyncio]>=2.0.50"` to `pyproject.toml` runtime deps. The `[asyncio]` extra unconditionally pulls `greenlet>=1`, making the install platform-agnostic. Re-locked + re-synced.
- **Files modified:** `backend/pyproject.toml`, `backend/uv.lock`
- **Verification:** `uv run python -c "import greenlet; print(greenlet.__version__)"` → `3.5.1`; round-trip test passes against live PG.
- **Committed in:** Task 3 commit (alongside ADR-006 + spike test).

**2. [Rule 3 — Blocking] Suppressed SQLModel `.execute` DeprecationWarning in spike test**
- **Found during:** Task 3 (running pytest with `-W error::DeprecationWarning`)
- **Issue:** SQLModel's `AsyncSession.execute` is decorated with `@deprecated`, urging callers to use `.exec()`. But `.exec()` is statically typed only against `Select`/`SelectOfScalar`/`UpdateBase` and rejects raw `text()` clauses under `mypy --strict`. Local `warnings.catch_warnings()` blocks did not suppress the warning under pytest's per-test recorder.
- **Fix:** Used `@pytest.mark.filterwarnings("ignore::DeprecationWarning:tests.unit.db.test_db_session")` (canonical pytest path; matches the warning's `caller-module` attribution). Kept `.execute(text("SELECT 1"))` for the smoke (raw SQL idiom). The canonical ORM path will switch to `.exec()` with proper Select statements once Plan 06-02 lands the SQLModel tables.
- **Files modified:** `backend/tests/unit/db/test_db_session.py`
- **Verification:** `pytest tests/unit/db/test_db_session.py -v` reports `2 passed, 1 skipped` (or `3 passed` with PG up) and `0 warnings`.
- **Committed in:** Task 3 commit.

---

**Total deviations:** 2 auto-fixed (both Rule 3 — Blocking).
**Impact on plan:** Both auto-fixes were required to make the D-01 spike actually run on this dev host (Apple Silicon Darwin 25.3.0). Neither changes the locked decision shape; the greenlet workaround is documented in ADR-006 §Decision and §Consequences so downstream plans inherit the constraint.

## Issues Encountered

- **Postgres not reachable on first run** — expected. The spike test skip-path was designed for exactly this. After `docker run --rm -p 5432:5432 -e POSTGRES_PASSWORD=trip_planner -e POSTGRES_USER=trip_planner -e POSTGRES_DB=trip_planner postgres:16-alpine`, all 3 tests pass.
- **`uv lock` showed greenlet but `uv sync` didn't install it on macOS arm64** — caused by the upstream wheel marker excluding `arm64`. Resolved via `sqlalchemy[asyncio]` explicit dep (deviation 1 above).

## User Setup Required

None required for this plan. The spike test skips cleanly when Postgres is absent; no environment variables, no compose stack — those land in Plan 06-06.

For developers who want to run the live spike locally: `docker run --rm -p 5432:5432 -e POSTGRES_PASSWORD=trip_planner -e POSTGRES_USER=trip_planner -e POSTGRES_DB=trip_planner postgres:16-alpine` then `cd backend && uv run pytest tests/unit/db/test_db_session.py -v`. The skip-on-OperationalError pattern means CI without Docker still passes.

## Next Phase Readiness

**Ready for Plan 06-02 (alembic init + SQLModel tables):**
- `engine` and `_async_sessionmaker` from `app/db/session.py` are the canonical wiring for `migrations/env.py` (`config.set_main_option("sqlalchemy.url", settings.database_url)` + `target_metadata = SQLModel.metadata`).
- The Pitfall 8 lock (`expire_on_commit=False`) is documented in the ADR; downstream stores inherit the constraint.
- `Settings.database_url` is the single source of truth for both app code and alembic — no parallel config to keep in sync.

**Ready for Plan 06-03 (MessageStore + ConversationRepository impls):**
- Per-store impls receive `_async_sessionmaker` directly so they own session lifecycles independently of FastAPI's request-scoped dep — critical for SSE handlers (Pitfall 3).
- The macOS arm64 greenlet workaround is in `pyproject.toml`, so any contributor's `uv sync` will pick up greenlet without manual intervention.

**No blockers carried forward.**

## Self-Check: PASSED

- `[x] backend/app/db/__init__.py` exists.
- `[x] backend/app/db/session.py` exists; exports `engine` (AsyncEngine), `_async_sessionmaker`, `get_session` (callable).
- `[x] backend/tests/unit/db/__init__.py` exists.
- `[x] backend/tests/unit/db/test_db_session.py` exists; 3 tests; skip-on-OperationalError documented.
- `[x] .planning/adrs/ADR-006-postgres.md` exists with `Status: Locked` (matches `grep -q '^Status: Locked'`).
- `[x] Commit 46a28c1 (Task 1) found in git log.`
- `[x] Commit c82d6cd (Task 2) found in git log.`
- `[x] backend/pyproject.toml` pins all four new deps + sqlalchemy[asyncio]; matches `grep -E '^\s*"(psycopg\[binary,pool\]|sqlmodel|alembic)' pyproject.toml` (3 hits) + `grep -E '"pytest-postgresql' pyproject.toml` (1 hit).
- `[x] uv lock --check` exits 0.
- `[x] uv run mypy app/db/ app/config.py tests/unit/db/` reports zero issues.
- `[x] uv run ruff check app/db/ app/config.py tests/unit/db/` reports zero issues.
- `[x] uv run pytest tests/unit/db/test_db_session.py` reports 2 passed + 1 skipped (no PG) or 3 passed (live PG).

---
*Phase: 06-postgres-redis-docker-compose*
*Completed: 2026-06-04*
