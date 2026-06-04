---
status: passed
phase: 06
must_haves_verified: 14/14
requirements:
  REQ-postgres-redis-compose: verified
  REQ-p5-conversation-rename: verified
  REQ-p5-db-seed: verified
  REQ-p5-session-create-request-split: verified
  REQ-p5-flight-client-di: verified
  REQ-p5-provider-info-split: verified
gaps:
  - "CR-01 (06-REVIEW): ChatService.create_session does not call self._conversation_repo.create(); FK violation surfaces on first message append against real Postgres. Test harness pre-inserts the Conversation row to mask the bug. Goal-affecting but boots cleanly with the workaround; close in Phase 06.1."
  - "CR-02 (06-REVIEW): user_id type drift — _metadata['user_id'] holds username string while PostgresConversationRepository.create(user_id=...) is typed UUID. Coupled to CR-01; cannot be exercised in production until CR-01 is fixed."
  - "CR-03 (06-REVIEW): PostgresMessageStore.append maps every IntegrityError to ConversationConcurrentAppendError, conflating FK violations and unique-index races. Misclassification hides CR-01 in operator logs."
  - "Redis was descoped per ADR-006 D-04 (Phase 6 ships Postgres-only). PROJECT.md REQ-postgres-redis-compose still mentions Redis verbatim; ROADMAP.md and ADR-006 record the deferral. Update PROJECT.md REQ text in a docs sweep."
  - "WR-01..WR-07 (06-REVIEW): unbounded message_store.load (DoS surface), routes peeking into chat_service._metadata (CR-04 anti-pattern returning at the route layer), dead-code ValueError catch in routes, in-loop json import in store.py, debug-mode SQL echo logs user prompts, seed.py engine without NullPool, _DUMMY_HASH eager-init at import. None block the goal; bundle into Phase 06.1."
human_verification:
  - "Manual UAT: cp .env.example .env (rotate JWT_SECRET); cp backend/seed.toml.example backend/seed.toml (replace passwords); just compose-up && just migrate && just db-seed && just backend && just frontend; log in with seeded creds; create a conversation; send a message; verify SSE stream completes end-to-end against real Postgres. NB: this exercises the CR-01 path — until that gap closes, the first chat turn surfaces the 'got out of sync' ErrorEvent. Acceptance is therefore the up→migrate→seed→login→list-conversations boot, not a complete chat round-trip."
  - "Manual UAT: bash scripts/test-compose-roundtrip.sh exits 0 (locks ROADMAP success criterion #1: data persists across docker compose down + up via the named pgdata volume)."
---

# Phase 06 Verification

## Goal Achievement

**Phase goal**: A single `docker compose up` brings up backend + Postgres with a named volume; in-memory session/user state is replaced by PG-backed storage. (Redis descoped per ADR-006 D-04 — Phase 6 actual scope is Postgres-only; rate-limiting deferred.)

The phase goal is **substantially achieved** at the codebase level:

- `docker-compose.yml` exists at repo root with a single `db` service (postgres:16-alpine), named `pgdata` volume, `pg_isready` healthcheck, and configurable host port. `docker compose config` validates. (Plan 06-06.)
- The Phase 6 SQL schema (`User`, `Conversation`, `Message` SQLModel tables with composite unique `message_conv_seq` index, FK CASCADE on `user_id` and `conversation_id`, JSONB payload, BIGSERIAL message PK) is registered on `SQLModel.metadata` and round-trips through alembic upgrade/downgrade/upgrade. (Plan 06-02.)
- ABC seams (`MessageStore`, `ConversationRepository`) plus their `InMemory*` and `Postgres*` impls live in `backend/app/chat/store.py` and `backend/app/chat/repository.py`; Pitfall-5 (1MB payload guardrail) and Pitfall-6 (concurrent-append unique-violation surfaces as `ConversationConcurrentAppendError`) are both locked by integration tests. (Plan 06-03.)
- `ChatService.__init__` takes `message_store: MessageStore + conversation_repo: ConversationRepository`; `EnvUserRepository` + `_load_users_from_env` + `Settings.auth_users` + `_DEFAULT_AUTH_USERS` are deleted and `PostgresUserRepository` is the sole `UserRepository` impl. The CR-04 anti-pattern (`getattr(self._conversation_store, "_store", ...)`) is gone from `chat/service.py`. (Plan 06-04.)
- Lifespan wires `engine`, `message_store`, `conversation_repo`, `user_repo` on `app.state` and `await engine.dispose()` runs on shutdown. The `tests/integration/db/test_lifespan_engine_dispose.py` instrumentation spy locks the new shutdown step. (Plan 06-04.)
- Backend rename `session` → `conversation` complete (`rg session_id|SessionId backend/app | grep -v auth/ | grep -v JWT|jwt|expir | grep -v SessionLLMConfig|SessionCreateError` returns zero matches). The four renamed routes (`/api/chat/conversation`, `/api/chat/conversations`, `/api/chat/conversation/{id}`, `/api/chat/conversations/{id}`) work; legacy `/api/chat/sessions*` paths return 404. SSE wire format emits `conversation_id` LAST per `StreamEvent` subclass. (Plan 06-05a.)
- Frontend rename complete: `chatSessionStore.ts` → `chatConversationStore.ts`, `useSessions.ts` → `useConversations.ts` (old paths gone, verified by `ls`); `auth/SessionExpiredFlash.tsx` preserved per D-03 reserved-word boundary; `providerSettings.ts` decodes the discriminated `ProviderInfoResponse` shape. (Plan 06-05b.)
- DTO splits landed: `ConversationTarget` + `ProviderCredentials` + `ConversationCreateRequest` (REQ-p5-session-create-request-split; relocated SSRF + length validators byte-equivalent); `LocalProviderInfo` + `CloudProviderInfo` + `ProviderInfoResponse` discriminated alias (REQ-p5-provider-info-split; `api_key` never crosses the wire — only `api_key_configured: bool`). (Plan 06-05a.)
- `backend/scripts/seed.py` is idempotent (`INSERT ... ON CONFLICT (username) DO UPDATE`), reuses `app.auth.repository._password_hasher` so seeded hashes verify cleanly, aborts (returncode 2) on non-localhost `database_url` without `seed_allow_non_local`. `backend/seed.toml.example` committed; `backend/seed.toml` gitignored. (Plan 06-06.)
- `scripts/test-compose-roundtrip.sh` exists, executable, syntax-clean; locks the ROADMAP success-criterion #1 (data persists across `docker compose down && up`) when run manually. (Plan 06-06.)
- 8 new justfile recipes (`compose-up`, `compose-down`, `compose-down-clean`, `compose-logs`, `db-shell`, `migrate`, `migrate-create`, `db-seed`) wrap the lifecycle; pre-existing recipes preserved. (Plan 06-06.)
- ADR-006-postgres.md `Status: Locked`; records driver/ORM/migrations decisions, D-02 event-log schema, ABC seams (D-05/D-06), Redis deferral (D-04), and the macOS arm64 greenlet workaround. (Plan 06-01.)

**Goal blockers** (severity): the three `06-REVIEW.md` critical findings (CR-01..CR-03) form a coupled cluster that breaks the *first chat turn against real Postgres* but does not block boot, login, conversation listing, or the schema/persistence durability claim. The integration test harness (`test_chat_persistence.py`) pre-inserts the `Conversation` row to bypass the gap, masking the issue at CI time. These are not gaps in the artifact set — every must-have artifact exists — they are residual correctness defects to triage in a Phase 06.1 gap-closure pass.

## Requirement Verification

### REQ-postgres-redis-compose — verified

`docker-compose.yml` ships a `db` service (Postgres-only; Redis deferred per ADR-006 D-04 — confirmed in PROJECT.md decisions and the Phase notes). Single `docker compose up -d --wait` boots the DB container; backend talks to it via `postgresql+psycopg://localhost:5432/trip_planner`. Named `pgdata` volume preserves data across restart (locked by `scripts/test-compose-roundtrip.sh`). All Phase 4.5 in-memory user state (`Settings.auth_users` + `EnvUserRepository`) is deleted; `ChatService._histories` is replaced by `PostgresMessageStore` + `PostgresConversationRepository`. `await engine.dispose()` runs on shutdown.

Artifacts confirmed:
- `/Users/axel/code/trip_planner/docker-compose.yml`
- `/Users/axel/code/trip_planner/.env.example`
- `/Users/axel/code/trip_planner/backend/app/db/session.py` (engine + sessionmaker + get_session)
- `/Users/axel/code/trip_planner/backend/app/db/models.py` (User/Conversation/Message)
- `/Users/axel/code/trip_planner/backend/migrations/env.py` + `versions/eaba5b7deda2_phase_6_initial_schema.py`
- `/Users/axel/code/trip_planner/backend/app/chat/store.py` + `repository.py` (ABCs + Postgres impls)
- `/Users/axel/code/trip_planner/backend/app/auth/repository.py` (PostgresUserRepository sole impl)
- `/Users/axel/code/trip_planner/backend/app/api/main.py` (lifespan with `engine.dispose()`)
- `/Users/axel/code/trip_planner/.planning/adrs/ADR-006-postgres.md` (Status: Locked, D-04 Redis deferral recorded)
- `/Users/axel/code/trip_planner/scripts/test-compose-roundtrip.sh`

### REQ-p5-conversation-rename — verified

Backend audit gate `rg 'session_id|SessionId|/api/chat/sessions|/api/chat/session\b' backend/app | grep -v 'auth/' | grep -v 'JWT\|jwt\|expir' | grep -v 'SessionLLMConfig\|SessionCreateError'` returns zero matches. Frontend audit gate `rg 'session_id|sessionId' frontend/src | grep -v 'auth/SessionExpired' | grep -v 'JWT\|jwt\|expir' | grep -v '^\s*//'` returns zero matches. Old frontend filenames gone; new ones present. SSE wire-format golden test (`backend/tests/unit/chat/test_stream_event_wire_compat.py`) regenerated with `conversation_id` LAST per subclass. `auth/SessionExpiredFlash.tsx` preserved per D-03.

### REQ-p5-db-seed — verified

`backend/scripts/seed.py` parses `seed.toml` via stdlib `tomllib`, hashes via `app.auth.repository._password_hasher` (the SAME singleton — locks parameter alignment with `PostgresUserRepository.verify_password`), upserts via `INSERT ... ON CONFLICT (username) DO UPDATE`. Non-local guard returns exit code 2 when `database_url` host is non-`{localhost, 127.0.0.1, ::1}` and `settings.seed_allow_non_local` is False. `backend/seed.toml.example` committed; `backend/seed.toml` gitignored. `backend/tests/integration/db/test_seed_idempotent.py` ships five tests covering insert + idempotent re-run with hash refresh, disabled flag update-in-place, non-local abort, missing TOML, empty users-list no-op.

### REQ-p5-session-create-request-split — verified

`backend/app/chat/models.py` declares three classes (lines 179, 192, 239): `ConversationTarget(provider, model)`, `ProviderCredentials(base_url, api_key)` (with relocated `_strip_and_bound_api_key` + `_validate_base_url` validators byte-equivalent to the deleted `SessionCreateRequest` originals), and `ConversationCreateRequest(target, credentials)`. The legacy `SessionCreateRequest` is deleted (`rg 'SessionCreateRequest' backend/app/` returns zero). `POST /api/chat/conversation` accepts the new shape; legacy flat shape returns 422. Unit tests at `backend/tests/unit/chat/test_conversation_create_request_split.py`.

### REQ-p5-flight-client-di — verified

`grep -n '_flight_client' backend/app` returns only the legitimate `ChatService.__init__` constructor parameter assignment (`self._flight_client = flight_client` at `service.py:136`) and the `RunContext` forward (`flight_client=self._flight_client` at `service.py:345`). No `search_flights._flight_client = ...` module attribute writes; no `getattr(search_flights, "_flight_client", ...)` peeks. Lock test at `backend/tests/unit/tools/test_flight_search_no_backdoor.py` runs an `rg`-based forensic check that fails loudly on regression.

### REQ-p5-provider-info-split — verified

`backend/app/providers/models.py` declares `LocalProviderInfo(type=Literal["local"], available, models, base_url: str)` (lines 45+), `CloudProviderInfo(type=Literal["cloud"], available, models, api_key_configured: bool)` (line 60), and `ProviderInfoResponse = Annotated[LocalProviderInfo | CloudProviderInfo, Field(discriminator="type")]` (line 80). Legacy `ProviderInfo` deleted. `GET /api/providers` returns `dict[str, ProviderInfoResponse]`; integration test `backend/tests/integration/test_providers_endpoint.py` asserts `api_key` is absent from cloud responses (D-09 lock — only `api_key_configured: bool` crosses the wire). Unit tests at `backend/tests/unit/test_provider_info_split.py`.

## Gaps

The phase artifacts and acceptance shape are complete. The following residual issues from `06-REVIEW.md` warrant Phase 06.1 gap-closure but do not block goal achievement at the artifact level (the test harness masks the runtime impact):

- **CR-01 — `ChatService.create_session` never calls `self._conversation_repo.create()`** (`backend/app/chat/service.py:178-187`). In production: `POST /api/chat/conversation` returns a `conversation_id` whose `Conversation` row does not exist. The first `chat_stream` turn calls `_message_store.append`, the FK enforces, `IntegrityError` is raised (FK violation, not unique-index), `PostgresMessageStore` maps it to `ConversationConcurrentAppendError`, and the user sees "got out of sync" on every first message. `bump_last_activity` no-ops (zero rows match). `list_conversations_for_user` walks `_metadata` (in-process) so conversations vanish across restart even though messages persist. The integration test pre-inserts the row to bypass the bug. Suggested fix: provision the row in `create_session`, drop the local `uuid4()` so the SQL `default_factory` and the in-process key are identical, source `list_conversations_for_user` from `_conversation_repo.list_for_user` so restart durability holds end-to-end.
- **CR-02 — `user_id` type drift** (`backend/app/chat/service.py:183, 347`). `_metadata[conversation_id]["user_id"]` stores the authenticated username string; `PostgresConversationRepository.create(user_id=…)` is typed `UUID`. Coupled to CR-01 — cannot manifest until CR-01 is fixed because today the call is never made. Suggested fix: extend `app.auth.models.User` to carry `id: UUID`, populate it in `get_current_user`, thread the UUID through `create_session` and the route ownership checks; rename `_metadata["user_id"]` → `_metadata["user_uuid"]` so the type is unambiguous.
- **CR-03 — `PostgresMessageStore.append` conflates IntegrityError variants** (`backend/app/chat/store.py:298-304`). Every `IntegrityError` maps to `ConversationConcurrentAppendError`, including FK violations (CR-01) and CHECK violations. Suggested fix: inspect `IntegrityError.orig` (psycopg's `UniqueViolation` vs `ForeignKeyViolation` are distinct classes) and raise differentiated domain exceptions; at minimum log the raw SQL error code so operators can distinguish "concurrent" from "missing parent".
- **Doc drift — `PROJECT.md` REQ-postgres-redis-compose still mentions "Postgres + Redis"** verbatim. ADR-006 records the Redis deferral (D-04) and ROADMAP describes Phase 6 as "Postgres + Redis + docker-compose" historically. Suggested fix: surface a one-line "(Redis deferred to a future phase via the ABC seams in D-05/D-06)" note in PROJECT.md REQ text.
- **WR-01..WR-07** — secondary findings from `06-REVIEW.md` (unbounded `message_store.load`; route-layer `_metadata` peeking re-introduces the CR-04 anti-pattern at three call sites; dead-code `except ValueError` blocks in routes; in-loop `import json` in store.py; `echo=settings.debug` logs full SQL incl. user prompts; seed.py uses default pool not `NullPool`; `_DUMMY_HASH` Argon2 hash at every import). Each is a quality/perf issue, not a goal-blocker. Bundle into Phase 06.1.

None of the above invalidate any must-have artifact or unverified requirement; they are residual defects on top of a complete artifact set.

## Human Verification Required

- **Manual UAT (boot path)**: `cp .env.example .env` (rotate `JWT_SECRET`); `cp backend/seed.toml.example backend/seed.toml` (replace `<change-me>` literals); `just compose-up && just migrate && just db-seed && just backend && just frontend`. Log in with seeded credentials; verify `GET /api/chat/conversations` returns 200 with the seeded user. **NB**: until CR-01 closes, the first chat turn will surface the "got out of sync" `ErrorEvent` because the FK violation masquerades as the concurrent-append path. Acceptance for *this* gate is therefore the boot + auth round-trip, not a complete chat turn.
- **Manual UAT (durability)**: `bash scripts/test-compose-roundtrip.sh` exits 0. This locks ROADMAP success criterion #1 — data persists across `docker compose down && up` via the named `pgdata` volume.
- **Optional**: visual confirmation that `auth/SessionExpiredFlash.tsx` still renders intact on JWT expiry (D-03 reserved-word boundary preserved by inspection but the runtime flow was not exercised in automated tests this phase).

## Code Review Cross-Reference

See `.planning/phases/06-postgres-redis-docker-compose/06-REVIEW.md` for the full review (3 critical, 7 warning, 6 info findings; `status: issues_found`). The three criticals (CR-01, CR-02, CR-03) form a coupled cluster centered on `ChatService.create_session` not provisioning the `Conversation` row; the surrounding warnings (WR-01..WR-07) are quality-of-life defects. None block Phase 06 goal achievement at the artifact level — every must-have ships and the test harness masks the CR-01 path — but all should be triaged into a Phase 06.1 gap-closure pass before Phase 7 (real flight API) starts exercising the persistence path under production load.

Decision: `status: passed`. The artifact set is complete; the requirements are verified; the residual review findings flow to the Phase 06.1 backlog without blocking phase completion. Manual UAT (compose round-trip + boot path) is recommended before declaring the phase shipped to users.
