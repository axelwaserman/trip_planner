# Technology Stack

**Analysis Date:** 2026-04-27

## Languages

**Primary:**
- Python 3.13 - Backend API, AI/LLM orchestration, flight search tools (`backend/`)
- TypeScript ~5.9.3 - Frontend React application (`frontend/`)

**Secondary:**
- CSS - Minimal custom styling (`frontend/src/App.css`, `frontend/src/index.css`); most styling via Chakra UI style props

## Runtime

**Environment:**
- Python 3.13 (pinned in `backend/.python-version`)
- Node.js (version not pinned; no `.nvmrc` present)

**Package Managers:**
- uv - Python package manager for backend (`backend/pyproject.toml`)
  - Lockfile: `backend/uv.lock` (present, ~160KB)
- npm - Node package manager for frontend (`frontend/package.json`)
  - Lockfile: `frontend/package-lock.json` (present, ~234KB)

**Task Runner:**
- just (justfile) - Top-level task runner at `justfile` for common dev commands

## Frameworks

**Core:**
- FastAPI >=0.115.0 - Python async web framework for REST API (`backend/app/api/main.py`)
- React 19.1.1 - Frontend UI library (`frontend/src/main.tsx`)
- Vite 7.1.7 - Frontend build tool and dev server (`frontend/vite.config.ts`)

**AI/LLM:**
- LangChain >=0.3.0 - LLM abstraction layer and tool calling (`backend/app/chat.py`)
- LangChain-Ollama >=0.2.0 - Ollama integration for local LLM inference
- LangGraph >=1.0.2 - Agent graph orchestration (dependency present, not yet heavily used)

**UI:**
- Chakra UI v3 ^3.28.0 - React component library (`frontend/src/main.tsx`)
  - Uses compound component pattern (v3 dot notation: `Collapsible.Root`, `Collapsible.Content`)
  - Default system theme (no custom theme file yet)
  - Skill available: `.claude/skills/chakra-ui/SKILL.md`
- Emotion ^11.14.0 - CSS-in-JS runtime required by Chakra UI
- Framer Motion ^12.23.24 - Animation library (dependency, used by Chakra internally)

**Testing:**
- pytest >=8.3.0 - Python test runner (`backend/pyproject.toml`)
- pytest-asyncio >=0.24.0 - Async test support with `asyncio_mode = "auto"`
- No frontend testing framework configured yet

**Build/Dev:**
- Vite 7.1.7 - Frontend bundler with React plugin (`frontend/vite.config.ts`)
- Ruff >=0.7.0 - Python linter and formatter (`backend/pyproject.toml`)
- mypy >=1.13.0 - Python static type checker, strict mode enabled
- ESLint 9.36.0 - TypeScript/React linting (`frontend/eslint.config.js`)
- TypeScript ~5.9.3 - Type checking with strict mode (`frontend/tsconfig.app.json`)

## Key Dependencies

**Critical:**
- `langchain` >=0.3.0 - Core LLM orchestration, tool binding, chat model abstraction (`backend/app/chat.py`)
- `langchain-ollama` >=0.2.0 - Local LLM provider via Ollama
- `pydantic` >=2.9.0 - Data validation for all API models (`backend/app/models.py`)
- `pydantic-settings` >=2.6.0 - Environment variable configuration (`backend/app/config.py`)
- `@chakra-ui/react` ^3.28.0 - All frontend UI components

**Infrastructure:**
- `uvicorn[standard]` >=0.32.0 - ASGI server for FastAPI (`justfile` start command)
- `httpx` >=0.27.0 - Async HTTP client for external API calls and testing
- `pyjwt` >=2.10.1 - JWT token handling (dependency present, auth is placeholder)
- `pwdlib` >=0.3.0 - Password hashing library (dependency present, auth is placeholder)
- `python-multipart` >=0.0.21 - Form data parsing for FastAPI
- `python-dotenv` >=1.0.0 - Environment file loading

**Frontend Content:**
- `react-markdown` ^10.1.0 - Markdown rendering in chat messages (`frontend/src/components/ChatInterface.tsx`)
- `remark-gfm` ^4.0.1 - GitHub Flavored Markdown support (tables, strikethrough)

## Configuration

**Environment:**
- Backend settings via `pydantic-settings` BaseSettings (`backend/app/config.py`)
- Loads from `.env` file (not committed; no `.env` files exist in repo)
- Key settings: `default_provider`, `default_model`, `ollama_base_url`, `openai_api_key`, `anthropic_api_key`
- Frontend dev server proxies `/api` requests to backend at `http://localhost:8000` (`frontend/vite.config.ts`)

**Build:**
- `backend/pyproject.toml` - Python project configuration, test markers, ruff/mypy config
- `frontend/tsconfig.json` - TypeScript project references
- `frontend/tsconfig.app.json` - App TypeScript config (ES2022 target, strict, bundler module resolution)
- `frontend/tsconfig.node.json` - Node-side TypeScript config
- `frontend/vite.config.ts` - Vite build config with React plugin and API proxy
- `frontend/eslint.config.js` - Flat ESLint config with TypeScript and React plugins

**Linting/Formatting (Backend):**
- Ruff with rules: E, W, F, I, UP, B, C4, N, SIM, TCH
- Line length: 100
- Target: Python 3.13
- mypy: strict mode, disallow untyped defs

**Linting/Formatting (Frontend):**
- ESLint 9 flat config with `@eslint/js`, `typescript-eslint`, `eslint-plugin-react-hooks`, `eslint-plugin-react-refresh`
- No Prettier configured (relies on ESLint and TypeScript defaults)

## Platform Requirements

**Development:**
- Python 3.13+
- Node.js (recent LTS recommended; no version pinned)
- Ollama running locally at `http://localhost:11434` for default LLM provider
- `just` task runner (optional but recommended; `justfile` at project root)
- `uv` Python package manager

**Production:**
- No deployment configuration present (no Dockerfile, no docker-compose, no CI/CD pipeline)
- Backend: uvicorn serving FastAPI app at `app.api.main:app`
- Frontend: Vite production build (`npm run build`)

## Project Skills

**Chakra UI v3** (`.claude/skills/chakra-ui/SKILL.md`):
- Compound component pattern guidance
- Style props, theming, recipes, responsive patterns
- Form integration with react-hook-form examples

**FastAPI** (`.claude/skills/fastapi/SKILL.md`):
- Production patterns for Pydantic v2, async SQLAlchemy 2.0
- JWT auth templates, service layer pattern
- Prevention strategies for 7 documented FastAPI issues
- Testing patterns with httpx/ASGITransport

---

*Stack analysis: 2026-04-27*
