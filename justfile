# Trip Planner - Just Commands

# Install all dependencies
install:
    cd backend && uv sync --dev
    cd frontend && npm install

# Run backend server
backend:
    cd backend && uv run uvicorn app.api.main:app --reload --host 127.0.0.1 --port 8000

# Run frontend dev server
frontend:
    cd frontend && npm run dev

# Run all backend tests (unit + integration + e2e via path discovery)
test:
    cd backend && uv run pytest

# Run only E2E tests with real LLM
test-e2e:
    cd backend && uv run pytest -m "e2e" -v -s

# Run real-API Amadeus integration tests (requires AMADEUS_API_KEY + AMADEUS_API_SECRET; skipped without)
test-amadeus:
    cd backend && uv run pytest tests/e2e_amadeus/ -v

# Run unit tests only
test-unit:
    cd backend && uv run pytest tests/unit/

# Run integration tests only  
test-integration:
    cd backend && uv run pytest tests/integration/

# Lint backend code
lint:
    cd backend && uv run ruff check .

# Format backend code
format:
    cd backend && uv run ruff format .

# Type check backend
typecheck:
    cd backend && uv run mypy app/

# Run all checks (lint + format + typecheck)
check:
    cd backend && uv run ruff check .
    cd backend && uv run ruff format --check .
    cd backend && uv run mypy app/

# Auto-fix linting issues
fix:
    cd backend && uv run ruff check --fix .
    cd backend && uv run ruff format .

# Build frontend for production
build:
    cd frontend && npm run build

# Run Playwright e2e UAT (full smoke + visual regression)
uat:
    cd frontend && npm run test:e2e

# Run Playwright SSE smoke pack only (~30s; needs backend running)
uat-smoke:
    cd frontend && npm run test:e2e:smoke

# Run Playwright visual regression only
uat-visual:
    cd frontend && npm run test:e2e:visual

# Refresh Playwright visual baselines after intended UI changes
uat-baselines:
    cd frontend && npm run test:e2e:update-baselines

# Clean build artifacts
clean:
    find . -type d -name "__pycache__" -exec rm -rf {} +
    find . -type d -name ".pytest_cache" -exec rm -rf {} +
    find . -type d -name ".mypy_cache" -exec rm -rf {} +
    find . -type d -name ".ruff_cache" -exec rm -rf {} +
    rm -rf backend/dist
    rm -rf frontend/dist

# Phase 6 — compose + migrations + seed

# Bring the compose db service up and wait for healthcheck (compose v2.18+)
compose-up:
    docker compose up -d --wait

# Stop compose; pgdata named volume is preserved (data survives restart)
compose-down:
    docker compose down

# Stop compose AND drop the pgdata volume — destructive
compose-down-clean:
    docker compose down -v

# Tail the db container logs
compose-logs:
    docker compose logs -f db

# Open psql shell against the running compose db
db-shell:
    docker compose exec db psql -U trip_planner -d trip_planner

# Apply all alembic migrations (host-side uv env; compose only runs the DB)
migrate:
    cd backend && uv run alembic upgrade head

# Generate a new alembic migration from the SQLModel metadata diff
migrate-create MSG:
    cd backend && uv run alembic revision --autogenerate -m "{{MSG}}"

# Idempotent seed: upserts users from backend/seed.toml into the user table
db-seed:
    cd backend && uv run python scripts/seed.py
