# Trip Planner - Architecture & Code Patterns

**Last Updated**: 2026-05-20

## Core Design Principles

1. **Async-First**: All I/O operations use `async/await` (FastAPI, LangChain, aiohttp)
2. **Type Safety**: Full mypy strict mode, explicit type hints everywhere
3. **Dependency Injection**: FastAPI `Depends()` for clients and services
4. **SOLID Principles**: Abstract clients, service layer, domain models
5. **Testing**: Unit + integration + E2E tests (aim for >80% coverage)

---

## Named Patterns

### Data Model Pattern
**When to use**: Data structures the program manipulates

**Location**: `models.py` inside each domain package. After the Phase 4.9 split the
monolithic `app/domain/models.py` no longer exists; models now live in their
respective domain packages:

| Domain | Module |
|--------|--------|
| Auth (User, UserInDB) | `app/auth/models.py` |
| Chat events + session DTOs | `app/chat/models.py` |
| Provider discovery + errors | `app/providers/models.py` |
| Flight queries + results | `app/flights/models.py` |

**Rules**:
- Pydantic models only
- No business logic except validators and basic getters/setters
- Act like structs to avoid using `dict`
- Explicit type annotations always

**Example**:
```python
# app/flights/models.py
from pydantic import BaseModel, Field, field_validator, model_validator
from datetime import date, datetime
from typing import Self

class FlightQuery(BaseModel):
    origin: str = Field(..., min_length=3, max_length=3)
    destination: str = Field(..., min_length=3, max_length=3)
    departure_date: date
    return_date: date | None = None
    passengers: int = Field(default=1, ge=1, le=9)

    @field_validator("origin", "destination")
    @classmethod
    def validate_iata_code(cls, v: str) -> str:
        code = v.upper()
        if not re.match(r"^[A-Z]{3}$", code):
            raise ValueError(f"Invalid IATA code: {v}. Must be 3 letters A-Z.")
        return code

    @model_validator(mode="after")
    def validate_departure_not_in_past(self) -> Self:
        if self.departure_date < datetime.now().date():
            raise ValueError("Departure date cannot be in the past")
        return self
```

---

### Abstract Client Pattern
**When to use**: Stateful/complex business logic, external API integrations

**Structure**:
```
FlightAPIClient (ABC)
    ├── MockFlightAPIClient
    └── AmadeusFlightAPIClient  (Phase 7, not yet implemented)
```

**Rules**:
- Domain-specific ABC at top level
- Multiple concrete implementations
- All methods are `async def`
- Custom exceptions for error handling (`FlightSearchError`)

**Example**:
```python
# app/tools/flight_client.py
class FlightAPIClient(ABC):
    @abstractmethod
    async def health_check(self) -> bool: ...

    @abstractmethod
    async def search(
        self,
        query: FlightQuery,
        sort_by: SortBy = "price",
        max_price: Decimal | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[Flight]: ...

    @abstractmethod
    async def get_flight_details(self, flight_id: str) -> Flight: ...

class MockFlightAPIClient(FlightAPIClient):
    async def search(self, query: FlightQuery, ...) -> list[Flight]:
        # Generates deterministic mock data from a seed
        ...
```

---

### Functional Service Pattern
**When to use**: Stateless/simple business logic

**Rules**:
- Pure functions when possible
- Use decorators for cross-cutting concerns (retry, logging)
- No class state
- Explicit parameters, no globals

**Example**:
```python
# app/services/formatting.py
from app.utils.retry import with_retry

@with_retry(max_attempts=3)
async def format_flight_results(
    flights: list[Flight],
    sort_by: str = "price"
) -> str:
    """Format flight results for LLM consumption."""
    sorted_flights = sorted(flights, key=lambda f: getattr(f, sort_by))
    return "\n".join(f"- {f.origin} → {f.destination}: ${f.price}" for f in sorted_flights)
```

---

### Dependency Injection Pattern
**When to use**: Always for services, clients, and stores

**Rules**:
- Use FastAPI `Depends()` for injection
- Factory functions return instances
- Store singletons in `app.state` (via lifespan context)
- Never use `@lru_cache` for singletons (violates DI)

**Example**:
```python
# app/api/dependencies.py
from fastapi import Depends
from app.infrastructure.clients.flight import FlightAPIClient
from app.infrastructure.clients.mock import MockFlightAPIClient

def get_flight_client() -> FlightAPIClient:
    """Factory for flight API client."""
    return MockFlightAPIClient()

# app/api/routes/flights.py
from fastapi import APIRouter, Depends

router = APIRouter()

@router.post("/api/flights/search")
async def search_flights(
    query: FlightQuery,
    client: FlightAPIClient = Depends(get_flight_client),
) -> list[Flight]:
    service = FlightService(client=client)
    return await service.search_flights(query)
```

---

### LLMProvider Factory Pattern
**When to use**: Any code that needs to obtain a chat model. Do not construct
`ChatOllama` / `ChatOpenAI` / `ChatAnthropic` directly — use the factory.

**Location**:
- Protocol: `app/llm/protocol.py` — `LLMProvider` + `BoundProvider`
- Factory + DTO: `app/llm/factory.py` — `LLMProviderFactory`, `SessionLLMConfig`
- Concrete providers: `app/llm/providers/` (`ollama.py`, `openai.py`, `anthropic.py`, `lmstudio.py`)

**Structure**:
```
LLMProviderFactory          # per-app singleton on app.state.llm_factory
    └── build(SessionLLMConfig) → LLMProvider   # per-session, from protocol.py

LLMProvider (Protocol, @runtime_checkable)
    ├── get_provider_name() → str
    ├── validate_config()   → ProbeError | None
    ├── bind_tools(tools)   → BoundProvider
    └── list_models()       → list[str]

BoundProvider (Protocol, @runtime_checkable)    # return type of bind_tools()
    ├── ainvoke(messages)   → AIMessage
    └── astream(messages)   → AsyncIterator[AIMessageChunk]
```

**Rules**:
- Concrete providers (`OllamaProvider`, etc.) satisfy `LLMProvider` via duck
  typing — they do **not** subclass the Protocol. `@runtime_checkable` makes
  `isinstance(provider, LLMProvider)` work for conformance tests.
- `LLMProvider.bind_tools()` returns `BoundProvider`, which deliberately does
  **not** expose `bind_tools` again. Re-binding would silently drop session state.
- `SessionLLMConfig` is a `@dataclass(frozen=True)` — immutable by policy.
- `api_key` lives only in the in-memory `SessionLLMConfig`; it is never logged
  or persisted (D-09). The `ApiKeyScrubber` log filter installed at startup
  redacts any accidental leaks.
- `LLMProviderFactory` is constructed once in `lifespan` and stashed on
  `app.state.llm_factory`. Routes access it via the `get_llm_factory` dependency.

**Example**:
```python
# app/llm/factory.py
@dataclass(frozen=True)
class SessionLLMConfig:
    provider: str
    model: str
    base_url: str | None
    api_key: str | None

class LLMProviderFactory:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def build(self, config: SessionLLMConfig) -> LLMProvider:
        match config.provider:
            case "ollama":
                return OllamaProvider(
                    model=config.model,
                    base_url=config.base_url or self._settings.ollama_base_url,
                    probe_timeout_seconds=self._settings.provider_probe_timeout_seconds,
                    reasoning_model_prefixes=self._settings.ollama_reasoning_model_prefixes,
                )
            case "openai":
                return OpenAIProvider(
                    model=config.model,
                    api_key=config.api_key or self._settings.openai_api_key,
                )
            ...
```

```python
# app/llm/protocol.py
@runtime_checkable
class LLMProvider(Protocol):
    def get_provider_name(self) -> str: ...
    async def validate_config(self) -> ProbeError | None: ...
    def bind_tools(self, tools: Sequence[BaseTool]) -> BoundProvider: ...
    async def list_models(self) -> list[str]: ...
```

---

### Discriminated StreamEvent Union Pattern
**When to use**: Any code that emits or consumes chat stream events
(`chat_stream`, SSE serialisation, frontend parsing).

**Location**: `app/chat/models.py`

**Structure**:

Five concrete event models, each with a `Literal` `type` discriminator, plus
a `StreamEvent` union alias used for annotations and `TypeAdapter` validation:

```
ContentEvent     type="content"     — LLM text chunk
ThinkingEvent    type="thinking"    — LLM reasoning token (Ollama qwen3/deepseek-r1 only)
ToolCallEvent    type="tool_call"   — tool dispatched (before execution)
ToolResultEvent  type="tool_result" — tool completed
ErrorEvent       type="error"       — tool or stream-level error
```

**Rules**:
- Do not instantiate `StreamEvent` directly; it is a `Field(discriminator="type")`
  annotated union alias, not a class.
- `ErrorEvent.error_code` is typed as `ErrorCode` (a `StrEnum` in the same
  module). Do not use bare strings for error codes — use the enum.
- `ErrorEvent.raw_detail` always passes through `_scrub()` before construction
  (see `app/llm/log_scrubbing.py`) so API keys cannot leak in error payloads.
- Wire-level `type` discriminator values are part of the frontend contract —
  do not rename them.

**Example**:
```python
# app/chat/models.py
class ErrorCode(StrEnum):
    session_error = "session_error"
    tool_error    = "tool_error"
    stream_error  = "stream_error"

class ErrorEvent(BaseModel):
    type:       Literal["error"] = "error"
    error_code: ErrorCode
    message:    str
    retryable:  bool
    tool_name:  str | None = None
    raw_detail: str | None = None
    session_id: str

StreamEvent = Annotated[
    ContentEvent | ThinkingEvent | ToolCallEvent | ToolResultEvent | ErrorEvent,
    Field(discriminator="type"),
]
```

---

### UserRepository Pattern
**When to use**: Any code that needs to look up or verify users. Do not access
`AUTH_USERS` / `app.state` directly from auth routes.

**Location**: `app/auth/repository.py`

**Structure**:
```
UserRepository (ABC)
    ├── get_user(username) → UserInDB     (raises UserNotFoundError if absent)
    └── verify_password(plain, hashed)   → bool

EnvUserRepository(UserRepository)        # Phase 4.x — reads AUTH_USERS env var
PostgresUserRepository(UserRepository)  # Phase 5 — database-backed (not yet implemented)
```

**Rules**:
- Auth routes depend on `UserRepository` (the ABC), not on `EnvUserRepository`.
- The active implementation is stashed on `app.state.user_repo` in `lifespan`
  and injected via the `get_user_repository` FastAPI dependency.
- Swapping implementations for Phase 5 requires only a single `dependency_overrides`
  change in `api/main.py` — zero route changes needed.
- `EnvUserRepository` uses Argon2 via `pwdlib`. Do not change the hasher
  without re-hashing all stored passwords.

**Example**:
```python
# app/auth/repository.py
class UserRepository(ABC):
    @abstractmethod
    def get_user(self, username: str) -> UserInDB: ...

    @abstractmethod
    def verify_password(self, plain: str, hashed: str) -> bool: ...

class EnvUserRepository(UserRepository):
    def __init__(self) -> None:
        self._users: dict[str, UserInDB] = _load_users_from_env()

    def get_user(self, username: str) -> UserInDB:
        user = self._users.get(username)
        if user is None:
            raise UserNotFoundError(username)
        return user
```

```python
# app/api/main.py (lifespan wiring)
app.state.user_repo = EnvUserRepository()
app.dependency_overrides[auth_routes.get_user_repository] = get_user_repository_override
```

---

### StrEnum for Cross-Module Taxonomies
**When to use**: Whenever the same set of stable string codes appears in more
than one file (e.g. a wire-level error code shared between a service layer and a
Pydantic response model). Define it once as a `StrEnum` and import it.

**Rule**: Never duplicate `Literal["a", "b", "c"]` unions across modules.
Define a `StrEnum` in the module closest to its meaning and import it everywhere
else. Wire-level values are part of the frontend contract — existing members
are immutable; new codes are appended only.

**Canonical examples**:

| StrEnum | Location | Consumed by |
|---------|----------|-------------|
| `ProbeErrorCode` | `app/llm/errors.py` | `ProbeError`, `SessionCreateError`, frontend `mapProbeError` |
| `ErrorCode` | `app/chat/models.py` | `ErrorEvent`, frontend error-routing logic |

**Example**:
```python
# app/llm/errors.py
class ProbeErrorCode(StrEnum):
    PROVIDER_UNREACHABLE = "provider_unreachable"
    MODEL_NOT_INSTALLED  = "model_not_installed"
    MISSING_API_KEY      = "missing_api_key"
    INVALID_API_KEY      = "invalid_api_key"

class ProbeError(BaseModel):
    error:   ProbeErrorCode
    message: str
    hint:    str

# app/providers/models.py
from app.llm.errors import ProbeErrorCode

class SessionCreateError(BaseModel):
    error:   ProbeErrorCode   # same enum, not a Literal copy
    message: str
    hint:    str
```

---

## LangChain 1.0 Integration

**Version**: LangChain 1.0.3 (with LangGraph)

### Key Patterns

**Tool Definition**:
```python
from langchain_core.tools import tool

@tool
def search_flights(
    origin: str,
    destination: str,
    departure_date: str,
    return_date: str | None = None,
    max_results: int = 5,
) -> str:
    """Search for flights between two airports.
    
    Args:
        origin: IATA code for departure airport (e.g., 'JFK')
        destination: IATA code for arrival airport (e.g., 'LHR')
        departure_date: Date in YYYY-MM-DD format
        return_date: Optional return date in YYYY-MM-DD format
        max_results: Maximum number of flights to return (1-10)
    
    Returns:
        JSON string with flight results including status, query, and results array.
    """
    # Implementation returns structured JSON for LLM
```

**LLM with Tools (Phase 4.5+)**:

LLM construction no longer happens at startup. The app builds a per-session
`LLMProvider` from `LLMProviderFactory.build(config)`, calls `bind_tools()` on it
to get a `BoundProvider`, and passes that to `ChatService.chat_stream`. See the
`LLMProvider` factory section below for the full pattern.

```python
# app/chat/service.py (simplified)
provider = factory.build(session_config)          # LLMProvider
bound    = provider.bind_tools([search_flights])  # BoundProvider
async for chunk in bound.astream(messages):
    # Handle content / tool_calls / reasoning_content
```

**No `create_agent()` needed** - LangChain 1.0 uses `bind_tools()` for function calling support.

---

## Error Handling Strategy

### Exception Hierarchy

```
APIError (base)
    ├── APITimeoutError (retryable)
    ├── APIRateLimitError (retryable)
    ├── APIServerError (retryable, 5xx)
    └── APIClientError (non-retryable, 4xx)

FlightSearchError (business logic errors)
```

### Retry Decorator

**Location**: `app/utils/retry.py`

**Features**:
- Exponential backoff
- Circuit breaker pattern
- Configurable max attempts
- Retry only on specific exceptions

**Usage**:
```python
from app.utils.retry import with_retry
from app.exceptions import APITimeoutError, APIServerError

@with_retry(
    max_attempts=3,
    backoff_factor=2.0,
    retryable_exceptions=(APITimeoutError, APIServerError),
)
async def call_external_api() -> dict:
    # API call that might fail transiently
    ...
```

---

## Testing Strategy

### Test Pyramid

1. **Unit Tests** (70%):
   - Individual functions/classes
   - Mock all external dependencies
   - Fast execution (<1s per test)
   - 100% coverage for business logic

2. **Integration Tests** (20%):
   - API endpoints with TestClient
   - Service layer with real dependencies
   - Database interactions (future)
   - Medium execution (~2-5s per test)

3. **E2E Tests** (10%):
   - Full request → response flow
   - Mock external APIs only
   - Real LLM interactions (mocked in CI)
   - Slow execution (~5-10s per test)

### Testing Patterns

**Mocking External APIs**:
```python
# tests/conftest.py
@pytest.fixture
def mock_flight_client() -> FlightAPIClient:
    client = Mock(spec=FlightAPIClient)
    client.search.return_value = [create_mock_flight()]
    return client

# tests/test_flight_service.py
async def test_search_flights(mock_flight_client):
    service = FlightService(client=mock_flight_client)
    results = await service.search_flights(query)
    assert len(results) > 0
```

**Testing Streaming**:
```python
# tests/test_chat_streaming.py
async def test_chat_stream_with_tool():
    async with httpx.AsyncClient() as client:
        async with client.stream("POST", "/api/chat/stream", json=request) as response:
            events = []
            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    events.append(json.loads(line[6:]))
            
            # Assert event types
            assert any(e["event_type"] == "tool_call" for e in events)
            assert any(e["event_type"] == "tool_result" for e in events)
```

---

## Architecture Decision Records (ADRs)

### ADR-001: LangChain 1.0 with bind_tools() Pattern

**Date**: 2025-11-10

**Status**: Accepted

**Context**: Need agent framework for tool calling with LLMs.

**Decision**: Use LangChain 1.0 `bind_tools()` pattern instead of older `create_agent()` approach.

**Rationale**:
- LangChain 1.0 uses LangGraph under the hood (more flexible)
- `bind_tools()` works with any chat model that supports function calling
- Simpler pattern: just bind tools to LLM, no separate agent object
- Easier to test (mock LLM directly)

**Consequences**:
- ✅ Cleaner code, less abstraction
- ✅ Works with streaming out of the box
- ✅ Easy to switch LLM providers
- ❌ Less guidance on agent patterns (more DIY)

---

### ADR-002: Global Chat Store (To Be Replaced)

**Date**: 2025-11-08

**Status**: Deprecated (replaced by Session Management in Pre-Phase 4)

**Context**: Need to maintain conversation history across requests.

**Decision**: Use global `_global_chat_store` dictionary with session IDs.

**Rationale**:
- Quick MVP implementation
- Built-in LangChain `InMemoryChatMessageHistory`
- No database required

**Consequences**:
- ❌ Global mutable state (anti-pattern)
- ❌ No multi-tab support (shared state)
- ❌ Memory leak (no cleanup)
- ❌ Not production-ready

**Replacement**: Session Management with `SessionStore` ABC (Pre-Phase 4 Task 1)

---

### ADR-003: Streaming with Server-Sent Events

**Date**: 2025-11-09

**Status**: Accepted

**Context**: Need real-time streaming of LLM responses to frontend.

**Decision**: Use Server-Sent Events (SSE) with `EventSourceResponse`.

**Rationale**:
- Native browser support (EventSource API)
- Simpler than WebSockets for unidirectional streaming
- Works with HTTP/1.1 (no HTTP/2 required)
- Easy to implement with FastAPI

**Consequences**:
- ✅ No additional libraries needed
- ✅ Auto-reconnect on connection loss
- ✅ Simple client implementation
- ❌ Unidirectional only (no client→server streaming)
- ❌ Limited to text data (JSON encoded)

---

### ADR-004: Pydantic Models for All Data Structures

**Date**: 2025-11-06

**Status**: Accepted

**Context**: Need data validation and serialization throughout the app.

**Decision**: Use Pydantic models for all data structures (no raw dicts).

**Rationale**:
- Built-in validation with clear error messages
- Automatic OpenAPI schema generation
- Type safety with mypy integration
- Serialization/deserialization for free

**Consequences**:
- ✅ Fewer bugs from invalid data
- ✅ Better IDE autocomplete
- ✅ Self-documenting API
- ❌ Slight performance overhead (negligible for our use case)

---

### ADR-005: Mock-First External API Integration

**Date**: 2025-11-10

**Status**: Accepted

**Context**: Need flight search functionality but don't want to depend on external API during development.

**Decision**: Build mock client first, real API later (Phase 5).

**Rationale**:
- Faster development (no API credentials needed)
- Reliable tests (no network flakiness)
- Abstract Client Pattern enables easy swap
- Can develop/test offline

**Consequences**:
- ✅ Fast iteration
- ✅ Deterministic tests
- ✅ No API costs during development
- ❌ Need to ensure mock matches real API behavior

---

## Technology Stack

### Backend
- **FastAPI** 0.120+ - Async web framework
- **LangChain** 1.0+ - LLM orchestration (with LangGraph)
- **langchain-ollama** - Ollama integration
- **langchain-openai** - OpenAI + LM Studio integration
- **langchain-anthropic** - Anthropic integration
- **Pydantic** 2.12+ - Data validation
- **pyjwt** + **pwdlib[argon2]** - JWT auth + password hashing
- **pytest** + **pytest-asyncio** - Testing
- **ruff** - Linting and formatting
- **mypy** - Static type checking (strict mode)
- **uvicorn** - ASGI server
- **httpx** - Async HTTP client (provider probes)

### Frontend
- **React** 18+ - UI library
- **TypeScript** 5+ - Type safety
- **Chakra UI** v3 - Component library
- **Vite** - Build tool
- **react-markdown** + **remark-gfm** - Markdown rendering

### Tooling
- **uv** - Fast Python package manager
- **just** - Command runner (like make)
- **Ollama** - Local LLM runtime

### Supported LLM Providers (Phase 4.5+)
The LLM is no longer a startup-time singleton. Each session picks a provider
and model from `SessionLLMConfig`; the factory builds the right `LLMProvider`.

| Provider | Local/Cloud | Notes |
|----------|-------------|-------|
| `ollama` | Local | Dynamic `list_models` via `/api/tags`; `reasoning=True` gated on model prefix |
| `lmstudio` | Local | Dynamic `list_models` via `/v1/models` |
| `openai` | Cloud | API key from payload or `OPENAI_API_KEY` env var |
| `anthropic` | Cloud | API key from payload or `ANTHROPIC_API_KEY` env var |

Default local model: **qwen3:8b** (supports function calling + reasoning tokens via Ollama)

---

## Project Structure

```
backend/
├── app/
│   ├── config.py            # Settings (Pydantic BaseSettings)
│   ├── exceptions.py        # Custom exception hierarchy
│   ├── api/
│   │   ├── main.py          # FastAPI application + lifespan
│   │   └── routes/
│   │       └── routes.py    # Chat, health, provider, and flight endpoints
│   ├── auth/                # Auth domain (Phase 4.9)
│   │   ├── models.py        # User, UserInDB
│   │   ├── repository.py    # UserRepository ABC + EnvUserRepository
│   │   ├── routes.py        # /api/auth/* endpoints
│   │   └── exceptions.py    # UserNotFoundError
│   ├── chat/                # Chat domain (Phase 4.7 / 4.9)
│   │   ├── models.py        # StreamEvent union + session DTOs
│   │   └── service.py       # ChatService (tool-calling loop + SSE)
│   ├── flights/             # Flight domain (Phase 4.9)
│   │   └── models.py        # FlightQuery, Flight, FlightSearchResult, etc.
│   ├── llm/                 # LLM provider abstraction (Phase 4.5)
│   │   ├── errors.py        # ProbeErrorCode (StrEnum) + ProbeError
│   │   ├── factory.py       # LLMProviderFactory + SessionLLMConfig
│   │   ├── log_scrubbing.py # ApiKeyScrubber log filter
│   │   ├── protocol.py      # LLMProvider + BoundProvider (uses typing.Protocol — see "Known Tech Debt" below)
│   │   └── providers/
│   │       ├── anthropic.py # AnthropicProvider
│   │       ├── lmstudio.py  # LMStudioProvider
│   │       ├── ollama.py    # OllamaProvider
│   │       └── openai.py    # OpenAIProvider
│   ├── providers/           # Provider discovery domain (Phase 4.5)
│   │   └── models.py        # ProviderInfo, SessionCreateError, ProviderRefreshResponse
│   ├── services/            # (empty — reserved for future functional services)
│   └── tools/
│       ├── flight_client.py # FlightAPIClient ABC → MockFlightAPIClient
│       ├── flight_search.py # @tool search_flights
│       └── retry.py         # Retry decorator
├── tests/
│   ├── unit/                # One module under test; MagicMock collaborators only
│   ├── integration/         # TestClient + MockLLM + MockFlightAPIClient
│   └── e2e/                 # Real HTTP; no real LLM (see e2e/README.md)
└── pyproject.toml           # Dependencies + tooling config

frontend/
├── src/
│   ├── App.tsx              # Main app component
│   ├── components/
│   │   ├── ChatInterface.tsx       # Chat UI with streaming
│   │   ├── ToolExecutionCard.tsx   # Tool call + result display
│   │   └── ThinkingCard.tsx        # LLM reasoning display
│   └── main.tsx
└── vite.config.ts           # Proxy to backend API
```

---

## Known Tech Debt

### `app/llm/protocol.py` uses `typing.Protocol`

The `LLMProvider` and `BoundProvider` interfaces in `app/llm/protocol.py` are defined as `typing.Protocol` (with `@runtime_checkable`), not `abc.ABC`. This pre-dates the project rule documented in `CLAUDE.md`:

> Abstract interfaces use `ABC`, never `Protocol`. Python abstract base classes are the project convention; `typing.Protocol` is reserved for third-party duck-typing compatibility only.

**Why it stayed**: at the time `protocol.py` was authored (Phase 4.5), the rule was a global Python pattern (`~/.claude/rules/python/patterns.md`) preferring Protocols. The repo-local rule reversing this came later via the `/dignified-python` skill.

**Migration plan**: convert both Protocols to ABCs as part of the Phase 6 PydanticAI migration — `bind_tools` retires from the interface at that point anyway, so the rework is a natural fit. Activate `/dignified-python` when doing the conversion.

**Until then**: do NOT add new `typing.Protocol`-based interfaces. New abstract types must be ABCs (see `app/auth/repository.py::UserRepository` and `app/tools/flight_client.py::FlightAPIClient` for the canonical pattern in this repo).

---

## Comments Philosophy

**Never comment what, only why:**

```python
# ❌ Bad: Says what the code does
# Loop through all flights and filter by price
filtered = [f for f in flights if f.price < max_price]

# ✅ Good: Explains why this approach was chosen
# Use list comprehension instead of filter() for 2x performance
# on small datasets (<1000 items) per benchmark results
filtered = [f for f in flights if f.price < max_price]
```

**When to comment:**
- Non-obvious business logic
- Performance optimizations
- Workarounds for library bugs
- Security considerations

**When NOT to comment:**
- Self-explanatory code
- Type annotations (use types instead)
- Function names that describe behavior
