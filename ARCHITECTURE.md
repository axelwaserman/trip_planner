# Trip Planner - Architecture & Code Patterns

**Last Updated**: 2025-11-13

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

**Location**: `models.py` files in each domain module

**Rules**:
- Pydantic models only
- No business logic except validators and basic getters/setters
- Act like structs to avoid using `dict`
- Explicit type annotations always

**Example**:
```python
# app/domain/models.py
from pydantic import BaseModel, Field, field_validator
from datetime import datetime

class Flight(BaseModel):
    flight_number: str
    origin: str
    destination: str
    departure_time: datetime
    arrival_time: datetime
    price: float = Field(gt=0)
    
    @field_validator("arrival_time")
    @classmethod
    def validate_times(cls, v: datetime, info) -> datetime:
        if "departure_time" in info.data and v <= info.data["departure_time"]:
            raise ValueError("Arrival must be after departure")
        return v
```

---

### Abstract Client Pattern
**When to use**: Stateful/complex business logic, external API integrations

**Structure**:
```
BaseAPIClient (ABC)
    └── FlightAPIClient (ABC)
        ├── MockFlightAPIClient
        └── AmadeusFlightAPIClient
```

**Rules**:
- Generic ABC at top level
- Domain-specific ABC extends it
- Multiple concrete implementations
- All methods are `async def`
- Implement retry logic + circuit breaker
- Custom exceptions for error handling

**Example**:
```python
# app/infrastructure/clients/base.py
from abc import ABC, abstractmethod

class BaseAPIClient(ABC):
    @abstractmethod
    async def health_check(self) -> bool:
        """Check if API is available."""

# app/infrastructure/clients/flight.py
class FlightAPIClient(BaseAPIClient):
    @abstractmethod
    async def search(self, query: FlightQuery) -> list[Flight]:
        """Search for flights."""
    
    @abstractmethod
    async def get_flight_details(self, flight_id: str) -> Flight:
        """Get detailed flight information."""

# app/infrastructure/clients/mock.py
class MockFlightAPIClient(FlightAPIClient):
    async def search(self, query: FlightQuery) -> list[Flight]:
        # Generate realistic mock data
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

**Agent with Tools**:
```python
from langchain_ollama import ChatOllama

# Create LLM
llm = ChatOllama(
    base_url=settings.ollama_base_url,
    model=settings.ollama_model,
    temperature=0.7,
)

# Bind tools
llm_with_tools = llm.bind_tools([search_flights_tool])

# Streaming with tools
async for chunk in llm_with_tools.astream(messages):
    # Handle different chunk types: content, tool_calls, etc.
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
- **Pydantic** 2.12+ - Data validation
- **pytest** + **pytest-asyncio** - Testing
- **ruff** - Linting and formatting
- **mypy** - Static type checking
- **uvicorn** - ASGI server
- **aiohttp** - Async HTTP client

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

### Current LLM
- **qwen3:8b** - Primary model (supports function calling + reasoning mode)

---

## Project Structure

```
backend/
├── app/
│   ├── main.py              # FastAPI application + lifespan
│   ├── chat.py              # ChatService with LangChain
│   ├── config.py            # Settings (Pydantic BaseSettings)
│   ├── exceptions.py        # Custom exception hierarchy
│   ├── api/
│   │   └── routes/          # API endpoints
│   │       ├── chat.py      # Chat + streaming
│   │       ├── health.py    # Health check
│   │       └── flights.py   # Flight search
│   ├── domain/
│   │   ├── models.py        # Core models (Flight, FlightQuery)
│   │   ├── session.py       # ChatSession model (Pre-Phase 4)
│   │   └── types.py         # Type aliases
│   ├── infrastructure/
│   │   ├── clients/         # External API clients
│   │   │   ├── base.py      # BaseAPIClient ABC
│   │   │   ├── flight.py    # FlightAPIClient ABC
│   │   │   └── mock.py      # MockFlightAPIClient
│   │   ├── llm/             # LLM provider abstraction (Pre-Phase 4)
│   │   │   ├── factory.py   # Provider factory
│   │   │   └── ollama.py    # OllamaProvider
│   │   └── storage/         # Data storage
│   │       └── session.py   # SessionStore ABC (Pre-Phase 4)
│   ├── services/
│   │   └── flight.py        # Flight business logic
│   ├── tools/
│   │   └── flight_search.py # LangChain tool functions
│   └── utils/
│       └── retry.py         # Retry decorator + circuit breaker
├── tests/
│   ├── unit/                # Unit tests (70%)
│   ├── integration/         # Integration tests (20%)
│   └── e2e/                 # End-to-end tests (10%)
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
