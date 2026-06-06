# Trip Planner

AI-powered trip planning assistant with conversational interface and real-time travel data integration.

## Quickstart

Two boot paths are supported. Use the compose-driven path on a fresh checkout;
the legacy direct path is preserved for fast inner-loop iteration.

### Compose-driven (recommended; first run on a fresh checkout)

Requires Docker Desktop (or any Docker engine) running.

```bash
# 1. Copy env templates and edit secrets
cp .env.example .env
# edit .env: replace JWT_SECRET (the placeholder is a literal hint, not a secret)
#   python -c "import secrets; print(secrets.token_urlsafe(48))"

cp backend/seed.toml.example backend/seed.toml
# edit backend/seed.toml: replace the `<change-me>` passwords for admin + demo

# 2. Bring the database up + apply migrations + seed users
just compose-up   # docker compose up -d --wait
just migrate      # alembic upgrade head
just db-seed      # idempotent INSERT ... ON CONFLICT into the user table

# 3. Backend (Terminal 1) and frontend (Terminal 2)
just backend
just frontend
```

Open http://localhost:5173.

#### Pitfall 4 — host port 5432 already in use

If something else (Homebrew Postgres, another compose stack) is bound to
`localhost:5432`, `just compose-up` will fail with `port is already allocated`.
Pick one fix:

- Stop the conflicting service: `brew services stop postgresql@*`
- Override the host port: set `POSTGRES_HOST_PORT=5433` in `.env` AND change
  the `5432` in `DATABASE_URL` to match.

#### Compose round-trip test

Proves data survives `docker compose down && up` (ROADMAP success criterion #1):

```bash
bash scripts/test-compose-roundtrip.sh
```

The script seeds a user, takes the stack down, brings it back up, and asserts
the user count is unchanged. It does NOT clean up afterward — the named
`pgdata` volume is the assertion target. For destructive cleanup use
`just compose-down-clean`.

### Direct (legacy fast-iteration path)

Assumes Postgres is reachable on `localhost:5432` (compose, Homebrew, or a
remote DB via `DATABASE_URL`).

```bash
just install
just backend     # Terminal 1
just frontend    # Terminal 2
```

This path is preserved for tight iteration loops where you don't want a
container restart between code changes. The DATABASE_URL must point at a
live Postgres or backend startup will fail.

### Duffel Flight API (Phase 7)

The real flight provider behind `FlightAPIClient` is Duffel. The lifespan
auto-falls-back to `MockFlightAPIClient` when no token is configured (D-01 /
D-02), so a fresh checkout boots without credentials.

**Signup.** Create a sandbox account at <https://duffel.com/>. Sandbox tokens
start with `duffel_test_*`; production tokens start with `duffel_live_*`.
Vendor onboarding flow is owned by Duffel — do not duplicate it here.

**Local development.** Set the token in either of two equivalent ways
(`.env` is gitignored — never put credentials in `.env.example`):

```bash
# Option A — shell export
export DUFFEL_API_TOKEN=duffel_test_...

# Option B — .env file (preferred for local dev)
echo 'DUFFEL_API_TOKEN=duffel_test_...' >> .env
```

`Settings.duffel_env` defaults to `test`, so a real token is picked up
automatically. To force the mock client even with a real token present
(useful when running unit/integration tests against a partial network),
set `DUFFEL_ENV=mock`. See `.env.example` for the full list of Duffel rows.

**Local test run.** With `DUFFEL_API_TOKEN` set:

```bash
just test-duffel    # runs backend/tests/e2e_duffel/ — 4 live tests
```

When `DUFFEL_API_TOKEN` is unset, the suite skips at collection time. The
default `just test`, `just test-unit`, `just test-integration`, and
`just test-e2e` targets do NOT run the Duffel suite live.

**CI configuration (admin).** The `duffel-e2e` job in
`.github/workflows/ci.yml` is gated on `vars.DUFFEL_E2E_ENABLED == 'true'`
AND reads `secrets.DUFFEL_API_TOKEN` into the runtime env. Configure both
under **Settings → Secrets and variables → Actions**:

1. **Variables** — add `DUFFEL_E2E_ENABLED` = `true` (this drives
   `vars.DUFFEL_E2E_ENABLED` in the workflow).
2. **Secrets** — add `DUFFEL_API_TOKEN` = `duffel_test_...` (or
   `duffel_live_*`).

If either is missing the job is fully skipped — PR CI never requires the
secret, and PRs from external forks never receive it.

**Pitfall 1.** If `test_real_search_returns_results` fails with `count=0`,
the Duffel sandbox is sparse for MAD→BCN on the chosen date. Switch the
test query to LON→NYC manually — the test does not auto-switch.

## Project Structure

```
trip_planner/
├── backend/          # FastAPI backend
│   ├── app/         # Application code
│   ├── tests/       # Tests
│   └── ...
├── frontend/         # React + TypeScript frontend
│   ├── src/         # Frontend code
│   └── ...
├── PLAN.md          # Implementation roadmap
└── copilot-instructions.md  # Development guidelines
```

## Tech Stack

### Backend
- **FastAPI** - Modern async Python web framework
- **LangChain** - LLM orchestration and agent framework
- **Ollama** - Local LLM (gpt-oss20b)
- **Python 3.13** - Latest Python with enhanced type system
- **uv** - Fast Python package manager
- **pytest** - Testing framework
- **ruff** - Linting and formatting
- **mypy** - Static type checking

### Frontend
- **React 19** - UI framework
- **TypeScript** - Type-safe JavaScript
- **Vite** - Lightning-fast build tool
- **Chakra UI v3** - Component library
- **Framer Motion** - Animations

## Development Workflow

1. **Start Ollama** (if not running):
   ```bash
   ollama serve
   ```

2. **Run backend** (Terminal 1):
   ```bash
   cd backend && uv run uvicorn app.api.main:app --reload
   ```

3. **Run frontend** (Terminal 2):
   ```bash
   cd frontend && npm run dev
   ```

4. **Open browser**: http://localhost:5173

## Features (Roadmap)

- [x] Project structure and tooling
- [ ] Chat interface with conversational AI
- [ ] LangChain agent with tool calling
- [ ] Mock flight search tool
- [ ] Real Amadeus API integration
- [ ] Database persistence (future)
- [ ] GraphQL API layer (future)
- [ ] Additional tools: hotels, restaurants, weather (future)

## Documentation

- [Implementation Plan](./PLAN.md) - Detailed roadmap with phases
- [Copilot Instructions](./copilot-instructions.md) - Development guidelines
- [Backend README](./backend/README.md) - Backend-specific docs
- [Frontend README](./frontend/README.md) - Frontend-specific docs

## Contributing

This is a learning project. See `copilot-instructions.md` for development philosophy and code quality standards.

## License

Private project
