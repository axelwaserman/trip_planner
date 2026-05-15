# CI/CD Workflow

> Copy to `.github/workflows/ci.yml`

```yaml
name: CI

on:
  push:
    branches: ["**"]
  pull_request:
    branches: [master]

concurrency:
  group: ${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true

jobs:
  backend:
    name: Backend (Python 3.13)
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: backend
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.13"
      - uses: astral-sh/setup-uv@v4
        with:
          version: "latest"
          enable-cache: true
          cache-dependency-glob: "backend/uv.lock"
      - run: uv sync --dev
      - run: uv run ruff check .
      - run: uv run ruff format --check .
      - run: uv run mypy app/
      - run: |
          uv run pytest \
            -m "not slow" \
            --cov=app \
            --cov-report=xml:coverage.xml \
            --cov-report=term-missing \
            --cov-fail-under=60 \
            -v
      - uses: codecov/codecov-action@v4
        with:
          files: backend/coverage.xml
          flags: backend
          fail_ci_if_error: false
        env:
          CODECOV_TOKEN: ${{ secrets.CODECOV_TOKEN }}

  frontend:
    name: Frontend (Node 22)
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: frontend
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: "22"
          cache: "npm"
          cache-dependency-path: frontend/package-lock.json
      - run: npm ci
      - run: npm run lint
      - run: npx tsc --noEmit --project tsconfig.app.json

  e2e:
    name: E2E (Ollama required — manual/scheduled only)
    runs-on: ubuntu-latest
    if: github.event_name == 'workflow_dispatch' || github.event_name == 'schedule'
    defaults:
      run:
        working-directory: backend
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.13"
      - uses: astral-sh/setup-uv@v4
        with:
          version: "latest"
          enable-cache: true
          cache-dependency-glob: "backend/uv.lock"
      - run: uv sync --dev
      - name: Start Ollama
        run: |
          curl -fsSL https://ollama.com/install.sh | sh
          ollama serve &
          sleep 5
          ollama pull qwen3:4b
      - run: |
          uv run pytest \
            -m "e2e" \
            -v \
            --timeout=120
        env:
          OLLAMA_BASE_URL: http://localhost:11434
```

## Branch Protection (configure in GitHub UI)

**Settings → Branches → Branch protection rules → `master`:**

- [x] Require status checks to pass before merging
  - Required: `Backend (Python 3.13)`
  - Required: `Frontend (Node 22)`
- [x] Require branches to be up to date before merging
- [x] Do not allow bypassing the above settings

## Future Additions

| Phase | Addition |
|-------|----------|
| After Phase 4 | Add `npm run test:coverage` step to frontend job |
| After Phase 4 | Add frontend coverage threshold enforcement |
| After Phase 5 | Add `docker build` verification job |
| Later | Add deploy job triggered on merge to `master` |
