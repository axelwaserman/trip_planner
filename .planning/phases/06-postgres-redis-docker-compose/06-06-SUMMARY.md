---
phase: 06-postgres-redis-docker-compose
plan: 06
subsystem: infra
tags: [docker-compose, postgres, justfile, seed, dx, bootstrap, alembic]

requires:
  - phase: 06-postgres-redis-docker-compose / Plan 06-04
    provides: PostgresUserRepository + lifespan engine wiring + migrations against the user table
provides:
  - docker-compose.yml at repo root (single `db` service, postgres:16-alpine, named pgdata volume, healthcheck)
  - .env.example template (DATABASE_URL, POSTGRES_PASSWORD, JWT_SECRET; rotated default)
  - .gitignore guard for backend/seed.toml (real dev creds) while keeping the .example template tracked
  - 8 new justfile recipes (compose-up/down/down-clean/logs, db-shell, migrate, migrate-create, db-seed)
  - backend/scripts/seed.py — idempotent TOML→Postgres user upsert (REQ-p5-db-seed)
  - backend/seed.toml.example — committed placeholder (admin + demo, `<change-me>` literal)
  - scripts/test-compose-roundtrip.sh — executable acceptance script (locks ROADMAP success criterion #1)
  - README + CLAUDE.md updates documenting both the compose-driven and legacy-direct boot paths
affects:
  - Phase 7 (real flight API) — bootable stack ready for live integration tests
  - any future verifier or CI smoke job that needs a one-command DB

tech-stack:
  added: []  # No new packages — leverages psycopg/alembic/pwdlib already added in 06-01..06-04
  patterns:
    - Idempotent ON CONFLICT DO UPDATE seed (parameterised SQL, argon2 hash via the same pwdlib singleton as the auth repo)
    - Non-local-DB guard (returncode 2) gated on Settings.seed_allow_non_local
    - Compose-driven DX with named volume + healthcheck-aware `up --wait`
    - host-port override env var (Pitfall 4 escape hatch) without breaking the default 5432 binding

key-files:
  created:
    - docker-compose.yml
    - .env.example
    - backend/scripts/__init__.py
    - backend/scripts/seed.py
    - backend/seed.toml.example
    - backend/tests/integration/db/test_seed_idempotent.py
    - scripts/test-compose-roundtrip.sh
  modified:
    - .gitignore (backend/seed.toml ignored)
    - justfile (8 new recipes appended; pre-existing recipes untouched)
    - README.md (new Quickstart section with two boot paths + Pitfall 4 callout)
    - CLAUDE.md (## Commands section lists new compose/migrate/seed recipes)

key-decisions:
  - "Seed via parameterised INSERT ... ON CONFLICT (username) DO UPDATE — refreshes hash + disabled in place; re-running yields the same row count with a freshly-salted argon2 hash."
  - "Reuse `app.auth.repository._password_hasher` (the SAME PasswordHash([Argon2Hasher()]) singleton) so seeded hashes verify cleanly through PostgresUserRepository.verify_password without parameter drift."
  - "Generate user.id Python-side via uuid4() in the seed INSERT — the User SQLModel uses default_factory=uuid4 (no DB server_default for id), so a raw INSERT must supply it."
  - "Add a `sys.path` insert at the top of scripts/seed.py so `python scripts/seed.py` (the `just db-seed` invocation) resolves `app.*` imports without forcing a `python -m` invocation."
  - "Document both boot paths in README — compose-driven (recommended for fresh checkouts) and legacy-direct (preserved for fast iteration). Pitfall 4 host-port escape hatch surfaced inline."

patterns-established:
  - "One-shot scripts under backend/scripts/ — invoked as `cd backend && uv run python scripts/<name>.py` via a justfile recipe"
  - "Seed scripts hash secrets at write time, never at read time, and reuse the auth module's argon2 singleton for parameter alignment"
  - "Compose round-trip acceptance: a single bash script wraps the up→migrate→seed→count→down→up→count→assert sequence; the named volume IS the assertion target"

requirements-completed:
  - REQ-postgres-redis-compose
  - REQ-p5-db-seed

duration: ~30min
completed: 2026-06-04
---

# Plan 06-06: Postgres compose + DX layer + idempotent seed Summary

**docker-compose.yml at repo root, 8 new justfile recipes, and an idempotent `scripts/seed.py` that upserts users into the Phase 6 Postgres `user` table — closes the loop so a fresh checkout boots with `just compose-up && just migrate && just db-seed && just backend`.**

## Accomplishments

- Phase 6 stack now boots from a fresh checkout via `just compose-up && just migrate && just db-seed && just backend && just frontend` — the legacy direct path is preserved for fast iteration.
- `scripts/seed.py` is idempotent (re-running keeps the row count, refreshes the argon2 hash) and guarded against non-local execution (returncode 2 when `database_url` host is non-localhost and `seed_allow_non_local` is False).
- `scripts/test-compose-roundtrip.sh` proves data persists across `docker compose down && up` — locks ROADMAP success criterion #1.
- 5 new integration tests (`tests/integration/db/test_seed_idempotent.py`) cover: insert+idempotent re-run with hash refresh, disabled flag update-in-place, non-local abort, missing TOML, empty users-list no-op.

## Task Commits

Each task was committed atomically:

1. **Task 1: docker-compose.yml + .env.example + .gitignore + justfile** — `d0f8a36` (feat)
2. **Task 2: scripts/seed.py + seed.toml.example + integration tests** — `a2b2375` (feat)
3. **Task 3: round-trip script + README + CLAUDE.md updates** — `9d064c0` (feat)

## Files Created/Modified

- `docker-compose.yml` — single `db` service, postgres:16-alpine, pgdata named volume, pg_isready healthcheck, `${POSTGRES_HOST_PORT:-5432}:5432` binding
- `.env.example` — DATABASE_URL, POSTGRES_PASSWORD, JWT_SECRET (placeholder distinct from `_DEFAULT_JWT_SECRET = "changeme"` to force rotation), commented POSTGRES_HOST_PORT escape hatch
- `.gitignore` — adds `backend/seed.toml` while leaving `backend/seed.toml.example` tracked
- `justfile` — appends 8 recipes (`compose-up`, `compose-down`, `compose-down-clean`, `compose-logs`, `db-shell`, `migrate`, `migrate-create MSG`, `db-seed`); pre-existing recipes untouched
- `backend/scripts/__init__.py` — package marker so `from scripts.seed import seed` works in tests
- `backend/scripts/seed.py` — TOML → argon2 → INSERT ... ON CONFLICT upsert; reuses `_password_hasher` from `app.auth.repository`
- `backend/seed.toml.example` — committed template with `admin` + `demo` users + `<change-me>` literal passwords
- `backend/tests/integration/db/test_seed_idempotent.py` — 5 tests covering insert/idempotency/disabled-toggle/non-local guard/missing TOML/empty users
- `scripts/test-compose-roundtrip.sh` — 9-step bash acceptance script; executable; preserves pgdata for the assertion
- `README.md` — new Quickstart section with both boot paths + Pitfall 4 callout + round-trip-test subsection
- `CLAUDE.md` — `## Commands` block lists the new recipes alongside the existing ones; pointer to README for full bootstrap walkthrough

## Decisions Made

- **Python-side UUID for the seed INSERT**: the User SQLModel uses `default_factory=uuid4` and the alembic migration carried no DB-side server_default for `user.id`. Adding one would require a new migration, so `seed.py` generates the UUID at insert time and lets ON CONFLICT discard it for existing rows. (Documented inline in seed.py.)
- **`sys.path` adjustment in seed.py**: `python scripts/seed.py` adds `scripts/` (not `backend/`) to `sys.path`, so `from app.auth.repository import _password_hasher` would fail. Prepending the parent directory inside the script keeps the `just db-seed` invocation simple (no `python -m` required) and matches what the test importer already does via pytest's `pythonpath = ["."]`.
- **Reuse the `_password_hasher` singleton, not a new constructor**: ensures argon2 parameters (memory cost, time cost, parallelism) are byte-identical between seed-time and login-time, so seeded hashes verify cleanly through `PostgresUserRepository.verify_password`. Test `test_seed_inserts_and_is_idempotent_on_re_run` asserts `_password_hasher.verify("pw", hashed_after_seed) is True` to lock this alignment.

## Deviations from Plan

None on logic. The two implementation details above (Python-side UUID + sys.path tweak) were not spelled out in the plan but follow directly from the existing schema and the `just db-seed` invocation contract; both are documented inline.

## Issues Encountered

- **Host port 5432 collision during local verification.** The dev machine had a separate `travel_pal-postgres-1` container bound to `localhost:5432`. Used the documented Pitfall 4 escape hatch (`POSTGRES_HOST_PORT=5435`) plus a temporary side-load Postgres on the same port to run the integration tests; the `tests/integration/db/conftest.py` fixture is hardcoded to 5432 (CONTEXT.md D-10 default), so the test suite expects compose to be on the default port. The Pitfall 4 README/`.env.example` documentation surfaces this for downstream developers who hit the same collision.
- **Seed integration tests verified locally** by temporarily patching the conftest port to point at the side-load Postgres on 5435; conftest restored to 5432 before commit. All 5 tests passed in 2.44s.

## User Setup Required

None inside the codebase. The plan's `user_setup` block ("Confirm Docker Desktop is running before `just compose-up`" + "Stop Homebrew Postgres or use POSTGRES_HOST_PORT") is documented in README's Pitfall 4 callout.

## Next Phase Readiness

- Stack is bootable from a fresh checkout in three justfile recipes.
- `scripts/test-compose-roundtrip.sh` is the canonical acceptance gate for ROADMAP success criterion #1; downstream phases can rely on the named `pgdata` volume surviving routine compose restarts.
- Phase 7 (real flight API) inherits a working compose-up + migrate + seed pipeline with no extra infrastructure work; the only DB change Phase 7 needs is whatever it adds via `just migrate-create MSG`.

---
*Phase: 06-postgres-redis-docker-compose*
*Plan: 06-06*
*Completed: 2026-06-04*
