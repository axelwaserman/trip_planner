---
phase: 6
slug: postgres-redis-docker-compose
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-06-03
---

# Phase 6 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x (backend), vitest (frontend) |
| **Config file** | `backend/pytest.ini`, `frontend/vitest.config.ts` |
| **Quick run command** | `cd backend && uv run pytest tests/unit -x --tb=short` |
| **Full suite command** | `just test` (unit + integration + e2e via path discovery) |
| **Estimated runtime** | ~30s unit, ~3min integration (with compose db), ~13min full |

Wave 0 installs: `pytest-postgresql 8.1.0` (test DB fixtures), pinned `psycopg`, `sqlmodel`, `alembic` versions per RESEARCH §2.

---

## Sampling Rate

- **After every task commit:** Run `cd backend && uv run pytest tests/unit -x --tb=short`
- **After every plan wave:** Run `just test-unit && just test-integration` (integration requires `just compose-up && just migrate`)
- **Before `/gsd:verify-work`:** Full suite green; `docker compose down && docker compose up -d --wait && just db-seed` round-trip succeeds
- **Max feedback latency:** ~30 seconds for unit; ~180 seconds for integration

---

## Per-Task Verification Map

> Filled by planner per plan/task. Below are the validation **dimensions** each plan's tasks must hit. The planner converts these into per-task `<acceptance_criteria>` + `<automated>` blocks.

| Dimension | Requirement(s) | Test Type | Automated Command | Notes |
|-----------|----------------|-----------|-------------------|-------|
| psycopg async session works | REQ-postgres-redis-compose | unit | `pytest tests/unit/test_db_session.py -x` | D-01 spike output |
| SQLModel tables match alembic head | REQ-postgres-redis-compose | integration | `pytest tests/integration/test_migrations.py -x` | autogenerate-then-diff |
| MessageStore ABC contract holds (InMemory + Postgres) | REQ-postgres-redis-compose | unit + integration | `pytest tests/unit/test_message_store.py tests/integration/test_postgres_message_store.py -x` | shared contract test parametrized over both impls |
| ConversationRepository ABC contract holds | REQ-postgres-redis-compose | unit + integration | `pytest tests/unit/test_conversation_repository.py tests/integration/test_postgres_conversation_repository.py -x` | shared contract test |
| ChatService persists + replays via PG | REQ-postgres-redis-compose | integration | `pytest tests/integration/test_chat_persistence.py -x` | round-trip ModelMessage list |
| PostgresUserRepository replaces EnvUserRepository | REQ-postgres-redis-compose | integration | `pytest tests/integration/test_auth_pg.py -x` | login + token issuance against PG |
| `just db-seed` is idempotent | REQ-p5-db-seed | integration | `pytest tests/integration/test_seed_idempotent.py -x` | run twice, row count stable, hashes preserved |
| `session` → `conversation` rename complete | REQ-p5-conversation-rename | unit + integration | `pytest -k conversation -x && rg 'session_id\\|SessionId\\|/sessions' backend/app frontend/src` | grep-based forensic + behavior |
| `POST /api/chat/conversations` request schema split | REQ-p5-session-create-request-split | unit | `pytest tests/unit/test_chat_routes.py::test_conversation_create_request -x` | 422 on bad body |
| `flight_client` injected via FastAPI dep | REQ-p5-flight-client-di | unit | `pytest tests/unit/test_flight_tool_di.py -x` | confirm Phase 5 status; if unfinished, residual route plumbing |
| `ProviderInfoResponse` distinct from internal `ProviderInfo` | REQ-p5-provider-info-split | unit | `pytest tests/unit/test_provider_routes.py::test_response_schema -x` | response model not internal model |
| docker-compose up → migrate → seed → restart preserves data | REQ-postgres-redis-compose | manual + integration | `bash scripts/test-compose-roundtrip.sh` | acceptance from ROADMAP success criterion #1 |

---

## Wave 0 Requirements

- [ ] `backend/tests/integration/conftest.py` — `postgres_noproc` fixture (pytest-postgresql) pointed at compose `db`
- [ ] `backend/tests/unit/conftest.py` — `InMemoryMessageStore`, `InMemoryConversationRepository` fixtures
- [ ] `backend/tests/integration/fixtures/db.py` — template-clone helper for fast per-test schema
- [ ] `pytest-postgresql>=8.1.0` added to `backend/pyproject.toml` dev-deps
- [ ] `backend/tests/integration/test_message_store_contract.py` — shared contract test parametrized over (InMemory, Postgres)
- [ ] `backend/tests/integration/test_conversation_repository_contract.py` — shared contract test parametrized over (InMemory, Postgres)
- [ ] `scripts/test-compose-roundtrip.sh` — Bash script for compose-down/up data-preservation acceptance test

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| `docker compose up` reproducibility on fresh checkout | REQ-postgres-redis-compose | First-run host setup (`.env`, port 5432 collision check) cannot be safely automated | `git clone <repo>; cp .env.example .env; just compose-up; just migrate; just db-seed; just backend; just frontend` — verify chat round-trip in browser |
| Restart preserves conversation data | REQ-postgres-redis-compose | Requires `docker compose down` between writes | `just compose-up; <write a message>; docker compose down; just compose-up; <reload conversation>; verify history present` |
| Frontend `conversation_id` rename works end-to-end in browser | REQ-p5-conversation-rename | Visual + network panel inspection | Open devtools, send message, confirm `conversation_id` in URL/SSE/network, no `session_id` references |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags (CI mode only)
- [ ] Feedback latency < 30s for unit suite, < 180s for integration
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
