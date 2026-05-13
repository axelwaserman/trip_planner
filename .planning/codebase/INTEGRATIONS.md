# External Integrations

**Analysis Date:** 2026-04-27

## APIs & External Services

**LLM Providers (Multi-Provider Architecture):**

The application supports three LLM providers, selectable at session creation time via the `/api/providers` endpoint and `ProviderSelector` UI component.

- **Ollama** (Default) - Local LLM inference
  - SDK/Client: `langchain-ollama` via `langchain.chat_models.init_chat_model()`
  - Base URL: configured via `ollama_base_url` setting (default: `http://localhost:11434`)
  - Default model: `qwen3:4b`
  - Available models: `qwen3:4b`, `qwen3:8b`, `mistral:7b`, `deepseek-r1:8b`
  - Auth: None (local service)
  - Config file: `backend/app/config.py` (lines 20-23)
  - Initialization: `backend/app/api/main.py` (lines 37-42)
  - Always available (no credentials required)

- **OpenAI** (Optional) - Cloud LLM inference
  - SDK/Client: LangChain `init_chat_model()` with `model_provider="openai"`
  - Auth: `openai_api_key` env var
  - Default model: `gpt-4o-mini`
  - Available models: `gpt-4o`, `gpt-4o-mini`, `gpt-4-turbo`, `o1-mini`, `o3-mini`
  - Config file: `backend/app/config.py` (lines 25-26)
  - Availability gated on `bool(self.openai_api_key)` (line 60)

- **Anthropic** (Optional) - Cloud LLM inference
  - SDK/Client: LangChain `init_chat_model()` with `model_provider="anthropic"`
  - Auth: `anthropic_api_key` env var
  - Default model: `claude-3-5-sonnet-20241022`
  - Available models: `claude-3-5-sonnet-20241022`, `claude-3-5-haiku-20241022`, `claude-3-opus-20240229`
  - Config file: `backend/app/config.py` (lines 28-29)
  - Availability gated on `bool(self.anthropic_api_key)` (line 70)

**NOTE:** Currently only Ollama is wired up in the `lifespan()` function (`backend/app/api/main.py` lines 37-42). The OpenAI and Anthropic providers are configured in Settings but the session-level provider switching does NOT actually swap the LLM instance at runtime. Session metadata stores the selected provider/model but the same Ollama LLM is used for all sessions.

**Flight Search API:**
- **Mock Flight API** - Deterministic mock flight data generator
  - Client: `backend/app/tools/flight_client.py` (`MockFlightAPIClient`)
  - Abstract interface: `FlightAPIClient` ABC (same file, line 19)
  - Prepared for real API integration (Amadeus, etc.) via the abstract interface
  - No external API calls made; generates realistic flight data with seeded randomness
  - Tool binding: `backend/app/tools/flight_search.py` (LangChain `@tool` decorator)
  - Injection pattern: flight client set as attribute on tool function (`search_flights._flight_client`)

## Data Storage

**Databases:**
- None - No database configured
- No SQLAlchemy, no migrations, no database URLs in active configuration
- `pyjwt` and `pwdlib` are installed but unused in production code

**Session Storage:**
- In-memory Python dictionaries in `ChatService` (`backend/app/chat.py`)
  - `_histories: dict[str, InMemoryChatMessageHistory]` - Chat message history per session
  - `_metadata: dict[str, dict[str, str]]` - Session metadata (provider, model, created_at)
  - `_last_activity: dict[str, float]` - Last activity timestamp per session
  - Sessions expire after configurable `max_age_seconds` (default: 3600s)
  - All data lost on server restart

**File Storage:**
- Local filesystem only (no cloud storage)

**Caching:**
- None - No caching layer
- Flight client maintains a `_flight_cache` dict for looked-up flights (`backend/app/tools/flight_client.py` line 110)

## Authentication & Identity

**Auth Provider:**
- Placeholder/dummy implementation at `backend/app/api/routes/auth.py`
- Uses hardcoded `fake_users_db` dictionary with two test users
- `fake_hash_password()` just prepends "fakehashed" to the password
- Token is literally the username string (no JWT, no encryption)
- OAuth2PasswordBearer scheme configured at `/token` endpoint
- Endpoints: `POST /token` (login), `GET /users/me` (current user)
- **NOT production-ready** - explicitly a placeholder ("This doesn't provide any security at all")

**JWT Dependencies (Unused):**
- `pyjwt` >=2.10.1 - Installed but not imported anywhere in application code
- `pwdlib` >=0.3.0 - Installed but not imported anywhere in application code

## Monitoring & Observability

**Error Tracking:**
- None - No error tracking service (no Sentry, no Datadog)

**Logs:**
- Python `logging` module used in `backend/app/tools/retry.py`
- `print()` statements used for shutdown logging in `backend/app/api/main.py` (line 60)
- No structured logging, no log aggregation
- Frontend uses `console.log` / `console.error` for debugging

**Health Checks:**
- `GET /health` - Basic health check returning `{"status": "healthy"}` (`backend/app/api/routes/routes.py` line 170)
- No dependency health checks (no DB check, no LLM availability check)

## CI/CD & Deployment

**Hosting:**
- Not configured - Local development only

**CI Pipeline:**
- None - No CI/CD configuration files (no GitHub Actions, no Dockerfile)

**Build Commands:**
- Backend: `cd backend && uv run uvicorn app.api.main:app --reload --host 127.0.0.1 --port 8000`
- Frontend: `cd frontend && npm run build` (Vite production build)
- All commands defined in `justfile`

## Environment Configuration

**Required env vars (for default Ollama setup):**
- None strictly required - all have defaults in `backend/app/config.py`

**Optional env vars:**
- `OLLAMA_BASE_URL` - Ollama server URL (default: `http://localhost:11434`)
- `OLLAMA_MODEL` - Ollama model name (default: `qwen3:4b`)
- `DEFAULT_PROVIDER` - Default LLM provider (default: `ollama`)
- `DEFAULT_MODEL` - Default model name (default: `qwen3:4b`)
- `OPENAI_API_KEY` - Enables OpenAI provider (default: None)
- `OPENAI_MODEL` - OpenAI model (default: `gpt-4o-mini`)
- `ANTHROPIC_API_KEY` - Enables Anthropic provider (default: None)
- `ANTHROPIC_MODEL` - Anthropic model (default: `claude-3-5-sonnet-20241022`)
- `HOST` - Server host (default: `127.0.0.1`)
- `PORT` - Server port (default: `8000`)
- `DEBUG` - Debug mode (default: `True`)

**Secrets location:**
- `.env` file in backend directory (not committed, not present in repo)
- No secret manager configured

## Frontend-Backend Communication

**API Proxy:**
- Vite dev server proxies `/api/*` to `http://localhost:8000` (`frontend/vite.config.ts` lines 8-13)
- CORS configured for `http://localhost:5173` (Vite dev server) (`backend/app/api/main.py` lines 71-77)

**Streaming Protocol:**
- Server-Sent Events (SSE) for chat streaming
- Backend yields `data: {json}\n\n` formatted events (`backend/app/api/routes/routes.py` line 54)
- Frontend reads via `ReadableStream` / `response.body.getReader()` (`frontend/src/components/ChatInterface.tsx` line 125)
- Event types: `content`, `tool_call`, `tool_result`, `thinking`

**REST Endpoints:**
- `POST /api/chat` - Chat with SSE streaming response
- `POST /api/chat/session` - Create new chat session (with optional provider/model)
- `DELETE /api/chat/session/{session_id}` - Delete a session
- `GET /api/providers` - List available LLM providers and models
- `GET /health` - Health check
- `POST /token` - Dummy auth token endpoint
- `GET /users/me` - Dummy current user endpoint

**Client-Side State:**
- Provider/model selection persisted in `localStorage` key `llm_provider_config`
- Chat messages managed in React `useState` (not persisted)

## Webhooks & Callbacks

**Incoming:**
- None

**Outgoing:**
- None

---

*Integration audit: 2026-04-27*
