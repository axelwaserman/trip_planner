# Trip Planner - Architecture & Code Patterns

**Last Updated**: 2026-06-03

## Core Design Principles

1. **Async-First**: All I/O operations use `async/await` (FastAPI, PydanticAI, `pyreqwest` per ADR-008 — never `requests`, `aiohttp`, or `httpx`)
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
**When to use**: Any code that needs an LLM agent for a session. Do not
construct PydanticAI `OpenAIChatModel` / `AnthropicModel` / `Agent` directly —
use the factory.

**Location**:
- ABC: `app/llm/base.py` — `LLMProvider(ABC)` (renamed from `protocol.py` in Phase 5)
- Factory + DTO: `app/llm/factory.py` — `LLMProviderFactory`, `SessionLLMConfig`
- Concrete providers: `app/llm/providers/` (`ollama.py`, `openai.py`, `anthropic.py`, `lmstudio.py`)

**Structure**:
```
LLMProviderFactory                                # per-app singleton on app.state.llm_factory
    └── build(SessionLLMConfig) → LLMProvider     # per-session, from base.py

LLMProvider (ABC)                                 # single-tier; PydanticAI's Agent IS the tool-bound thing
    ├── get_provider_name() → str
    ├── validate_config()   → ProbeError | None
    ├── list_models()       → list[str]
    └── build_agent(tools, deps_type) → pydantic_ai.Agent[Deps, str]
```

**Rules**:
- Concrete providers (`OllamaProvider`, `OpenAIProvider`,
  `AnthropicProvider`, `LMStudioProvider`) explicitly subclass `LLMProvider`
  — ABC is the project convention per `CLAUDE.md` ("Abstract interfaces use
  `ABC`, never `Protocol`"). The Phase 4.5 `@runtime_checkable Protocol`
  shape and the `BoundProvider` second tier are both retired.
- `build_agent(tools, deps_type)` returns a `pydantic_ai.Agent[Deps, str]`.
  PydanticAI's `Agent` IS the tool-bound thing — there is no second tier.
  The Phase 4.5 `bind_tools` → `BoundProvider` indirection collapses.
- `SessionLLMConfig` is a `@dataclass(frozen=True)` — immutable by policy.
- `api_key` lives only in the in-memory `SessionLLMConfig`; it is never logged
  or persisted (D-09). The `ApiKeyScrubber` log filter installed at startup
  redacts any accidental leaks.
- `LLMProviderFactory` is constructed once in `lifespan` and stashed on
  `app.state.llm_factory`. Routes access it via the `get_llm_factory` dependency.
- `ChatService.create_session` calls `provider.validate_config()` and then
  `provider.build_agent(tools=[search_flights], deps_type=ChatDeps)`, storing
  the resulting `Agent[ChatDeps, str]` on `_agents[session_id]`. The Phase 4.5
  `_bound_providers` dict is gone.

**Per-provider model classes** (see `.planning/phases/05-pydanticai-migration/05-RESEARCH.md`
§ Per-Provider Migration Rules for full detail):

| Provider | PydanticAI model | PydanticAI provider |
|----------|------------------|---------------------|
| Ollama | `OpenAIChatModel(model, provider=OllamaProvider(base_url=...))` | `pydantic_ai.providers.ollama.OllamaProvider` |
| OpenAI (standard) | `OpenAIChatModel(model, provider=OpenAIProvider(api_key=...))` | `pydantic_ai.providers.openai.OpenAIProvider` |
| OpenAI (o-series) | `OpenAIResponsesModel(model, provider=OpenAIProvider(api_key=...))` | `pydantic_ai.providers.openai.OpenAIProvider` |
| Anthropic | `AnthropicModel(model, provider=AnthropicProvider(api_key=...))` | `pydantic_ai.providers.anthropic.AnthropicProvider` |
| LM Studio | `OpenAIChatModel(model, provider=OpenAIProvider(base_url=..., api_key=None))` | `pydantic_ai.providers.openai.OpenAIProvider` (no `api_key="lm-studio"` sentinel) |

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
                )
            case "openai":
                return OpenAIProvider(
                    model=config.model,
                    api_key=config.api_key or self._settings.openai_api_key,
                    o_series_prefixes=self._settings.openai_o_series_prefixes,
                )
            ...
```

```python
# app/llm/base.py
from abc import ABC, abstractmethod
from collections.abc import Sequence
from pydantic_ai import Agent

class LLMProvider(ABC):
    @abstractmethod
    def get_provider_name(self) -> str: ...
    @abstractmethod
    async def validate_config(self) -> ProbeError | None: ...
    @abstractmethod
    async def list_models(self) -> list[str]: ...
    @abstractmethod
    def build_agent(
        self, tools: Sequence[Any], deps_type: type[Any]
    ) -> Agent[Any, str]: ...
```

*(Phase 5 — replaces the Phase 4.5 two-tier `LLMProvider` Protocol +
`BoundProvider` Protocol shape. See ADR-007 for the locked decision.)*

---

### StreamEvent ABC Hierarchy
**When to use**: Any code that emits or consumes chat stream events
(`chat_stream`, SSE serialisation, frontend parsing).

**Location**: `app/chat/models.py`

**Structure**:

`StreamEvent(BaseModel, ABC)` is a base class with five concrete subclasses,
each carrying its own `Literal` `type` discriminator field:

```
StreamEvent (BaseModel, ABC)
    ├── ContentEvent      type="content"     — LLM text chunk
    ├── ThinkingEvent     type="thinking"    — LLM reasoning token (qwen3 <think> tags, Anthropic extended thinking, OpenAI o-series)
    ├── ToolCallEvent     type="tool_call"   — tool dispatched (before execution)
    ├── ToolResultEvent   type="tool_result" — tool completed
    └── ErrorEvent        type="error"       — tool or stream-level error
```

**Rules**:
- `StreamEvent` declares no `@abstractmethod` — it is purely a marker base
  for `isinstance(event, StreamEvent)` checks. Pydantic v2 supports
  `BaseModel + ABC` cleanly (verified in RESEARCH OQ-01 against pydantic 2.12.3).
- For union-style type annotations, use the explicit union
  `ContentEvent | ThinkingEvent | ToolCallEvent | ToolResultEvent | ErrorEvent`.
  The Phase 4.7 `Annotated[..., Field(discriminator="type")]` alias is retired.
- `ErrorEvent.error_code` is typed as `ErrorCode` (a `StrEnum` in the same
  module). Do not use bare strings for error codes — use the enum.
- `ErrorEvent.raw_detail` always passes through `_scrub()` before construction
  (see `app/llm/log_scrubbing.py`) so API keys cannot leak in error payloads.
- Wire-level `type` discriminator values are part of the frontend contract —
  do not rename them.
- **Wire format is byte-equivalent to Phase 4.7** (verified by golden-file
  test in `tests/unit/chat/test_stream_event_wire_compat.py`). Frontend
  `parseSSE.ts`, `useChat.ts`, and `types/chat.ts` are unchanged.

**Example**:
```python
# app/chat/models.py
from abc import ABC
from pydantic import BaseModel
from typing import Literal

class ErrorCode(StrEnum):
    session_error = "session_error"
    tool_error    = "tool_error"
    stream_error  = "stream_error"

class StreamEvent(BaseModel, ABC):
    """Base class for all SSE stream events. Marker-only — no abstract methods."""
    type: str
    session_id: str

class ErrorEvent(StreamEvent):
    type:       Literal["error"] = "error"
    error_code: ErrorCode
    message:    str
    retryable:  bool
    tool_name:  str | None = None
    raw_detail: str | None = None
```

*(Phase 5 — refactored from the Phase 4.7 discriminated-union alias as part of
REQ-p5-stream-event-abc, bundled with the LangChain → PydanticAI rewrite. See
ADR-007.)*

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

## PydanticAI Integration

**Version**: `pydantic-ai >= 0.8.1` (replaces LangChain in Phase 5; see ADR-007
at `.planning/adrs/ADR-007-pydantic-ai.md` for the locked decision).

### Key Patterns

**Tool Definition** (Phase 5):

Tools are plain `async def` functions whose first parameter is
`ctx: RunContext[ChatDeps]`. The Phase 2 `@tool` decorator from
`langchain_core.tools` is gone, and the `search_flights._flight_client`
attribute back-door used in Phase 4.x is **deleted** — `RunContext` is the
framework-managed replacement (D-06).

```python
from pydantic_ai import RunContext
from app.chat.deps import ChatDeps

async def search_flights(
    ctx: RunContext[ChatDeps],
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
    client = ctx.deps.flight_client  # framework-injected — not a monkey-patch
    # ... rest of body unchanged from Phase 4.x
```

**Per-turn dependency container** (D-05):

```python
# app/chat/deps.py
from dataclasses import dataclass
from app.tools.flight_client import FlightAPIClient

@dataclass(frozen=True)
class ChatDeps:
    flight_client: FlightAPIClient
    session_id: str
    user_id: str
```

`session_id` and `user_id` are carried so Phase 8 structured logging can
correlate tool calls without a Deps-shape churn.

**Per-session Agent construction** (D-04, D-07):

```python
# app/chat/service.py — ChatService.create_session (simplified)
provider = factory.build(session_config)            # LLMProvider (ABC)
err = await provider.validate_config()
if err is not None:
    raise SessionCreateError.from_probe(err)
agent = provider.build_agent(
    tools=[search_flights],
    deps_type=ChatDeps,
)                                                   # Agent[ChatDeps, str]
self._agents[session_id] = agent
```

**Streaming via `agent.iter()`** (D-12, D-15) — see RESEARCH § "Match block
pattern for the agent.iter() streaming loop" for the full canonical structure.
`agent.run_stream()` is **not** used in `ChatService` because tool events
must be emitted live; `run_stream` handles tools silently in `on_complete()`.

```python
# app/chat/service.py — ChatService.chat_stream (simplified)
from pydantic_ai import ModelRequestNode, CallToolsNode
from pydantic_ai.messages import (
    PartStartEvent, PartDeltaEvent,
    TextPart, ThinkingPart,
    TextPartDelta, ThinkingPartDelta,
    FunctionToolCallEvent, FunctionToolResultEvent,
    ToolCallPart, ToolReturnPart,
)

history = await self._conversation_store.load(session_id)
deps = ChatDeps(
    flight_client=self._flight_client,
    session_id=session_id,
    user_id=self._metadata[session_id]["user_id"],
)
async with self._agents[session_id].iter(
    message,
    message_history=history,
    deps=deps,
) as agent_run:
    async for node in agent_run:
        if isinstance(node, ModelRequestNode):
            async with node.stream(agent_run.ctx) as model_stream:
                async for event in model_stream:
                    match event:
                        case PartDeltaEvent(delta=ThinkingPartDelta(content_delta=d)) if d:
                            yield ThinkingEvent(chunk=d, session_id=session_id)
                        case PartDeltaEvent(delta=TextPartDelta(content_delta=d)) if d:
                            yield ContentEvent(chunk=d, session_id=session_id)
                        # PartStartEvent variants handled the same way; see RESEARCH
        elif isinstance(node, CallToolsNode):
            async with node.stream(agent_run.ctx) as tool_stream:
                async for event in tool_stream:
                    match event:
                        case FunctionToolCallEvent(part=ToolCallPart() as part):
                            yield ToolCallEvent(
                                tool_name=part.tool_name,
                                tool_args=_coerce_args(part.args),
                                session_id=session_id,
                            )
                        case FunctionToolResultEvent(result=ToolReturnPart() as ret):
                            yield ToolResultEvent(
                                tool_name=ret.tool_name,
                                tool_result=str(ret.content),
                                elapsed_ms=0,
                                session_id=session_id,
                            )

if agent_run.result is not None:
    await self._conversation_store.append(
        session_id,
        agent_run.result.new_messages(),
    )
```

**Reasoning-token extraction** (D-12, D-14):

- **Ollama qwen3** — native `<think>` tag parsing via
  `ModelProfile.thinking_tags` on `OllamaProvider`. No `reasoning=True` flag
  is needed; `chunk.additional_kwargs["reasoning_content"]` is gone.
- **OpenAI o-series** — `OpenAIResponsesModel` (Responses API) instead of
  `OpenAIChatModel`. `OpenAIProvider.build_agent()` dispatches on a model-name
  prefix list (`("o1", "o3")`) carried on `Settings`.
- **Anthropic extended thinking** — emitted automatically when the model
  returns `BetaThinkingBlock` / `BetaThinkingDelta`. (May require
  `extra_headers={"anthropic-beta": "thinking-in-streaming"}` — see ADR-007
  Open Risk OQ-R2.)

**Mock testing**:

`_MockLLMProvider.build_agent()` returns
`Agent(FunctionModel(stream_function=...), tools=..., deps_type=...)` so the
real PydanticAI streaming code path runs in tests. Mocking happens at the
`Model` level, not the `Agent` level, per the ADR-007 anti-pattern guidance.

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

**Testing Streaming** (mirrors `tests/integration/test_chat_service_flow.py`):
```python
def test_post_chat_streams_tool_events(client: TestClient, auth_headers: dict[str, str]) -> None:
    response = client.post(
        "/api/chat",
        json={"message": "Find flights", "session_id": session_id},
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert response.headers["content-type"] == "text/event-stream; charset=utf-8"
    body = response.text
    assert '"type":"tool_call"' in body
    assert '"type":"tool_result"' in body
    assert '"type":"content"' in body
```

Use FastAPI's `TestClient` rather than rolling an HTTP client by hand — it speaks SSE directly and avoids pinning the docs to any HTTP library (today `httpx` is still in the tree; ADR-008 migrates outbound HTTP to `pyreqwest`).

---

## Architecture Decision Records (ADRs)

### ADR-001: LangChain 1.0 with bind_tools() Pattern

**Date**: 2025-11-10

**Status**: Superseded by ADR-007 (Phase 5, 2026-06-03)

See `.planning/adrs/ADR-001-langchain.md` for the full standalone ADR
(including the supersession note pointing at
`.planning/phases/05-pydanticai-migration/05-CONTEXT.md` D-21 and the
superseding ADR-007). LangChain shipped through Phase 4.x and was
removed wholesale in Phase 5.

---

### ADR-007: PydanticAI Agent Pattern

**Date**: 2026-06-03

**Status**: Locked

**Supersedes**: ADR-001 (LangChain 1.0 with bind_tools())

See `.planning/adrs/ADR-007-pydantic-ai.md` for the full standalone ADR
(including RESEARCH OQ-01..OQ-05 verifications against installed
pydantic-ai 0.8.1, the per-provider migration rules table, and the
five-wave consequences breakdown). ADR-007 closes the
`LLMProvider`/`BoundProvider` Protocol-vs-ABC tech-debt entry and the
`search_flights._flight_client` Monkey-Patched Tool Dependency
anti-pattern carried through Phase 4.x.

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
- **PydanticAI** 0.8.1+ - LLM agent framework (`Agent[Deps, str]`, `RunContext`, `agent.iter()`); replaces LangChain in Phase 5 per ADR-007
- **Pydantic** 2.12+ - Data validation (floor raised to match pydantic-ai-slim's requirement)
- **pyjwt** + **pwdlib[argon2]** - JWT auth + password hashing
- **pytest** + **pytest-asyncio** - Testing
- **ruff** - Linting and formatting
- **mypy** - Static type checking (strict mode)
- **uvicorn** - ASGI server
- **`pyreqwest`** - Outbound HTTP client per ADR-008 (target; lands Phase 7 alongside real travel APIs). Provider probes and integration tests currently still use `httpx` and will migrate as part of ADR-008 — never add `aiohttp` or `requests`.

`langchain`, `langchain-core`, `langchain-ollama`, `langchain-openai`,
`langchain-anthropic`, and `langgraph` were all removed from `pyproject.toml`
in Phase 5 (Wave 4).

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
| `ollama` | Local | Dynamic `list_models` via `/api/tags`; `<think>` tag parsing native via PydanticAI `ModelProfile.thinking_tags` |
| `lmstudio` | Local | Dynamic `list_models` via `/v1/models`; no `api_key="lm-studio"` sentinel needed (Phase 5) |
| `openai` | Cloud | API key from payload or `OPENAI_API_KEY` env var; o-series models dispatched to `OpenAIResponsesModel` (Phase 5) |
| `anthropic` | Cloud | API key from payload or `ANTHROPIC_API_KEY` env var; extended thinking native via `BetaThinkingBlock` |

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
│   ├── chat/                # Chat domain (Phase 4.7 / 4.9 / 5)
│   │   ├── deps.py          # ChatDeps frozen dataclass for RunContext (Phase 5)
│   │   ├── models.py        # StreamEvent ABC + 5 concrete subclasses + session DTOs
│   │   ├── service.py       # ChatService (agent.iter() loop + SSE)
│   │   └── store.py         # ConversationStore ABC + InMemoryConversationStore (Phase 5)
│   ├── flights/             # Flight domain (Phase 4.9)
│   │   └── models.py        # FlightQuery, Flight, FlightSearchResult, etc.
│   ├── llm/                 # LLM provider abstraction (Phase 4.5 / 5)
│   │   ├── base.py          # LLMProvider(ABC) — renamed from protocol.py in Phase 5
│   │   ├── errors.py        # ProbeErrorCode (StrEnum) + ProbeError
│   │   ├── factory.py       # LLMProviderFactory + SessionLLMConfig
│   │   ├── log_scrubbing.py # ApiKeyScrubber log filter
│   │   └── providers/       # All four reshaped against pydantic_ai.models in Phase 5
│   │       ├── anthropic.py # AnthropicProvider (AnthropicModel + AnthropicProvider)
│   │       ├── lmstudio.py  # LMStudioProvider (OpenAIChatModel + OpenAIProvider, no api_key sentinel)
│   │       ├── ollama.py    # OllamaProvider (OpenAIChatModel + OllamaProvider; <think> tags native)
│   │       └── openai.py    # OpenAIProvider (OpenAIChatModel | OpenAIResponsesModel for o-series)
│   ├── providers/           # Provider discovery domain (Phase 4.5)
│   │   └── models.py        # ProviderInfo, SessionCreateError, ProviderRefreshResponse
│   ├── services/            # (empty — reserved for future functional services)
│   └── tools/
│       ├── flight_client.py # FlightAPIClient ABC → MockFlightAPIClient
│       ├── flight_search.py # search_flights(ctx: RunContext[ChatDeps], ...) — RunContext-injected (Phase 5)
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

## Anti-Pattern Closures (Phase 5)

The PydanticAI migration in Phase 5 closed two long-standing anti-pattern
entries that had been carried in this document since Phase 4.5 / 4.x. Both
are listed here for the historical record — neither is active tech debt
anymore.

| Anti-pattern | Closed in | How |
|--------------|-----------|-----|
| `search_flights._flight_client` monkey-patched dependency | Phase 5 (D-06) | Replaced with `RunContext[ChatDeps]` framework-managed DI; the back-door attribute and the `lifespan` line that wrote it are both deleted. Tools now declare `ctx: RunContext[ChatDeps]` as their first parameter and read `ctx.deps.flight_client`. |
| `LLMProvider` / `BoundProvider` Protocol-vs-ABC mismatch (Known Tech Debt) | Phase 5 (D-03) | Collapsed to a single `LLMProvider(ABC)` in `app/llm/base.py`. Concrete providers (`OllamaProvider`, `OpenAIProvider`, `AnthropicProvider`, `LMStudioProvider`) explicitly subclass the ABC. The `BoundProvider` second tier is retired entirely — PydanticAI's `Agent` IS the tool-bound thing, so no second tier is needed. |

See `.planning/adrs/ADR-007-pydantic-ai.md` for the locked decision and
`.planning/phases/05-pydanticai-migration/05-CONTEXT.md` D-01..D-21 for the
full set of Phase 5 architectural decisions.

**Rule going forward**: do NOT introduce `typing.Protocol`-based interfaces
for in-project abstract types. New abstract types must be ABCs (see
`app/auth/repository.py::UserRepository`, `app/tools/flight_client.py::FlightAPIClient`,
`app/chat/store.py::ConversationStore`, and `app/llm/base.py::LLMProvider`
for the canonical patterns in this repo).

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
