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

## Real Flight API (Phase 7 — in flux)

The backend ships only the in-process `MockFlightAPIClient` while Phase 7 is
re-planned around a new vendor (Duffel). The previous Amadeus integration was
removed after Amadeus closed self-service access. Once Phase 7 lands, this
section will document the Duffel credential setup and the gated CI job.

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
- **React 18** - UI framework
- **TypeScript** - Type-safe JavaScript
- **Vite** - Lightning-fast build tool
- **Chakra UI v3** - Component library
- **Framer Motion** - Animations

## Quick Start

### Prerequisites

- Python 3.13+
- Node.js 20+
- [uv](https://github.com/astral-sh/uv) - Install: `curl -LsSf https://astral.sh/uv/install.sh | sh`
- [Ollama](https://ollama.ai/) with gpt-oss20b model

### Backend Setup

```bash
cd backend

# Install dependencies
uv sync --dev

# Configure environment
cp .env.example .env

# Run server
uv run uvicorn app.api.main:app --reload --host 127.0.0.1 --port 8000

# Run tests
uv run pytest

# Lint and type check
uv run ruff check .
uv run mypy src/
```

Backend runs on http://localhost:8000

### Frontend Setup

```bash
cd frontend

# Install dependencies
npm install

# Run dev server
npm run dev
```

Frontend runs on http://localhost:5173

API calls to `/api/*` are automatically proxied to the backend.

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
