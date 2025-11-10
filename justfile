# Trip Planner - Just Commands

# Install all dependencies
install:
    cd backend && uv sync --dev
    cd frontend && npm install

# Run backend server
backend:
    cd backend && uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

# Run frontend dev server
frontend:
    cd frontend && npm run dev

# Run backend tests
test:
    cd backend && uv run pytest

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

# Clean build artifacts
clean:
    find . -type d -name "__pycache__" -exec rm -rf {} +
    find . -type d -name ".pytest_cache" -exec rm -rf {} +
    find . -type d -name ".mypy_cache" -exec rm -rf {} +
    find . -type d -name ".ruff_cache" -exec rm -rf {} +
    rm -rf backend/dist
    rm -rf frontend/dist
