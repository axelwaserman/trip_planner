# Trip Planner Backend

AI-powered trip planning assistant API built with FastAPI and LangChain 1.0.

## Prerequisites

- Python 3.13+
- [uv](https://github.com/astral-sh/uv) for dependency management
- [Ollama](https://ollama.ai/) with deepseek-r1:8b model

## Setup

1. **Install dependencies:**
   ```bash
   cd backend
   uv sync --dev
   ```

2. **Configure environment:**
   ```bash
   cp .env.example .env
   # Edit .env with your configuration
   ```

3. **Ensure Ollama is running:**
   ```bash
   # In a separate terminal
   ollama serve
   
   # Pull model if needed
   ollama pull deepseek-r1:8b
   
   # Verify model is available
   ollama list
   ```

## Development

**Quick commands (via justfile):**
```bash
# Run the development server
just run

# Run all quality checks (lint, format, typecheck)
just check

# Auto-fix formatting and linting
just fix

# Run tests
just test

# Run with coverage
just coverage
```

**Manual commands:**
```bash
# Run server
uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

# Run tests
uv run pytest

# Lint code
uv run ruff check .
uv run ruff format .

# Type check
uv run mypy app/
```

## API Documentation

Once running, visit:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## Project Structure

```
backend/
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI application
│   ├── chat.py              # LangChain chat service (with agents)
│   ├── config.py            # Configuration management
│   ├── exceptions.py        # Custom exception hierarchy
│   ├── api/
│   │   └── routes/          # API endpoints
│   │       ├── chat.py      # Chat endpoints (streaming SSE)
│   │       ├── health.py    # Health check
│   │       └── flights.py   # Flight search endpoints (Phase 3)
│   ├── domain/
│   │   ├── models.py        # Core domain models (Flight, FlightQuery)
│   │   └── types.py         # Type aliases
│   ├── infrastructure/
│   │   └── clients/         # External API clients
│   │       ├── base.py      # Base API client
│   │       ├── flight.py    # Flight API client interface
│   │       └── mock.py      # Mock flight client (Phase 3)
│   ├── services/
│   │   └── flight.py        # Flight business logic (Phase 3)
│   ├── tools/
│   │   └── flight_search.py # LangChain tool functions (Phase 3)
│   └── utils/
│       └── retry.py         # Retry decorator with circuit breaker
├── tests/
│   ├── test_chat.py
│   ├── test_exceptions.py
│   ├── test_flight_models.py
│   ├── test_health.py
│   ├── test_retry.py
│   ├── test_mock_client.py  # Phase 3
│   ├── test_flight_service.py  # Phase 3
│   ├── test_flights_api.py  # Phase 3
│   ├── test_flight_tool.py  # Phase 3
│   └── test_e2e.py          # Phase 3
├── pyproject.toml           # Dependencies & tooling config
├── .python-version          # Python version (3.13)
└── .env.example             # Environment template
```

## Architecture

### Core Design Principles
- **Async-first**: All I/O operations use `async/await` (FastAPI, LangChain, aiohttp)
- **Dependency injection**: FastAPI `Depends()` for clients and services
- **SOLID principles**: Abstract clients, service layer, domain models
- **Type safety**: Full mypy strict mode, explicit type hints everywhere
- **Testing**: Unit + integration + E2E tests (aim for >80% coverage)

### LangChain 1.0 Integration
This project uses **LangChain 1.0** with the new agent patterns:
- `create_agent()` from `langchain.agents` (built on LangGraph)
- Tools are **plain Python functions** (no decorators)
- Supports concurrent tool calls (multiple LLMs/tools)
- Async streaming with `agent.astream()`

### External API Client Pattern
```
BaseAPIClient (ABC)
    └── FlightAPIClient (ABC)
        ├── MockFlightAPIClient (Phase 3)
        └── AmadeusFlightAPIClient (Phase 5)
```

Each API client implements:
- `async def search()` - Core search functionality
- `async def health_check()` - Health monitoring
- Retry logic with exponential backoff
- Circuit breaker for persistent failures
- Custom exceptions for error handling

### Service Layer
Business logic lives in service classes with constructor injection:
```python
class FlightService:
    def __init__(self, client: FlightAPIClient):
        self.client = client
    
    async def search_flights(self, query: FlightQuery) -> list[Flight]:
        # Sorting, filtering, pagination logic
        flights = await self.client.search(query)
        return self._apply_business_logic(flights)
```

### Error Handling
```
APIError (base)
    ├── APITimeoutError (retryable)
    ├── APIRateLimitError (retryable)
    ├── APIServerError (retryable, 5xx)
    └── APIClientError (non-retryable, 4xx)

FlightSearchError (business logic errors)
```

## Development Workflow

### Pre-Commit Checklist
1. `just fix` - Auto-fix formatting and linting
2. `just typecheck` - Ensure no mypy errors
3. `just test` - All tests passing
4. Manual review of changes

### Conventional Commits
- `feat:` New features
- `fix:` Bug fixes
- `test:` Test additions/updates
- `docs:` Documentation changes
- `refactor:` Code refactoring
- `chore:` Maintenance tasks

## Technology Stack

- **FastAPI** 0.120+ - Async web framework
- **LangChain** 1.0+ - LLM orchestration (with LangGraph)
- **langchain-ollama** - Ollama integration
- **Pydantic** 2.12+ - Data validation
- **pytest** + **pytest-asyncio** - Testing
- **ruff** - Linting and formatting
- **mypy** - Static type checking
- **uvicorn** - ASGI server

## Future Roadmap
See [PLAN.md](../PLAN.md) for detailed implementation phases:
- ✅ Phase 1: Foundation & FastAPI Setup
- ✅ Phase 2: LangChain Integration & Chat Agent
- 🚧 Phase 3: Mock Flight Search Tool (in progress)
- 📋 Phase 4: Enhanced Frontend & LLM Provider Flexibility
- 📋 Phase 5: Real API Integration (Amadeus)
- 📋 Phase 6: Production Readiness
