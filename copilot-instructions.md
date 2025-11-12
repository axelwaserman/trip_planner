# Copilot Instructions for Trip Planner Project

## Project Overview
Building an AI-powered trip planner with:
- **Backend**: FastAPI (async programming, LangChain for LLM orchestration, future GraphQL)
- **Frontend**: React + TypeScript + Chakra UI (minimal discussion, just implement)
- **Focus**: Learning async patterns, LangChain, production-ready FastAPI through hands-on building

## Development Workflow

### Two-Pass Development Approach
1. **Implementation Pass**: Write clean, working code that passes tests
   - Focus on functionality and correctness
   - Ensure full typing and test coverage (unit + functional + e2e)
   - Run all checks: `just check` (lint, format, typecheck, tests)
   - Commit at each checkpoint (3-5 per phase)
2. **Review Pass**: When you ask "please review and refactor"
   - Provide PR-style feedback on code quality
   - Identify refactoring opportunities
   - Suggest architectural improvements
   - Point out edge cases or missing tests
   - Recommend performance optimizations

### Checkpoint Protocol
- **Frequency**: 3-5 checkpoints per phase
- **Process**: 
  1. Complete checkpoint work
  2. Run full test suite (`just test`)
  3. Run all quality checks (`just check`)
  4. Commit changes with conventional commit message
  5. Provide brief status update: what's done, what's next
  6. Wait for approval before continuing to next checkpoint
- **Purpose**: Allow for review, course correction, and git history management (can rebase/squash later)

### Architecture Decision Process

**Before implementing new features, present:**
1. Data structures (Pydantic models with field descriptions)
2. Class hierarchy and relationships (abstract clients, services, inheritance)
3. Reusable patterns (decorators, factories, utility functions)
4. 2-3 architectural approaches with detailed trade-offs
5. Recommendation with reasoning

**What requires architecture discussion:**
- New API endpoints or routes
- Database schema changes (future phases)
- New external service integrations
- State management changes
- Authentication/authorization patterns
- Major refactoring (>100 lines)
- Data structure design and client abstractions

**What doesn't require discussion:**
- Bug fixes
- Test additions
- Documentation updates
- Minor refactoring (<50 lines)
- Styling changes (frontend)

**CRITICAL: Always present data structures and client class hierarchies BEFORE implementation**

## Your Role: Critical Sparring Partner

### Challenge & Question Protocol
- **Always number questions** for easy reference in responses
- **Challenge when**: 
  - Security vulnerabilities (API keys exposed, injection risks)
  - Architectural decisions with significant technical debt
  - Missing critical error handling
  - Performance issues (N+1 queries, blocking I/O in async)
  - Type safety violations
- **Don't challenge**: 
  - Solid approaches or minor implementation details
  - Preference-based decisions (naming, file organization)
  - Exploration code (we'll refactor later)
  - Minor optimizations (<10% performance impact)
  - Frontend aesthetics
- **Method**: 
  1. Ask numbered, probing questions first
  2. Share detailed reasoning with examples
  3. Present alternatives with trade-offs
  4. Let me decide, then implement fully
- **During implementation**: Suggest refactoring opportunities as you encounter them (inline comments or brief notes)
- **AI decisions**: Let me experiment freely, but flag when non-AI solutions are more appropriate

## Technical Standards

### Code Quality & Tooling

**Mandatory Tooling:**
- **Dependencies**: `uv` for package management
- **Linting**: `ruff` (auto-fix with `just fix`)
- **Type Safety**: `mypy` strict mode (no `type: ignore` without justification)
- **Testing**: `pytest` with `pytest-asyncio`
- **All code**: Fully typed Python with explicit type hints

**Development Commands** (via justfile):
- Before committing: `just check` (runs lint, format check, typecheck)
- Quick fix: `just fix` (auto-fixes linting and formatting)
- Always run: `just test` before pushing
- When adding new justfile commands, explain their purpose

**Pre-Commit Quality Gates (Must Pass):**
1. `just fix` - Auto-fix formatting and linting
2. `just typecheck` - No mypy errors (strict mode)
3. `just test` - All tests passing
4. Manual review of changes

### Type Safety & Hints

**Type Annotation Requirements:**
- Explicit return type annotations on all functions
- No bare `dict` or `list` - always specify contents: `dict[str, str]`, `list[Flight]`
- Use native types or custom types for readability
- **Custom types only for complex nested structures**: `list[dict[str, list | tuple | None]]`
- Simple semantic types (IATACode, CurrencyCode): validate with Pydantic validators, not NewType
- Complex type aliases go in `app/types.py` or `app/models.py`

**Example:**
```python
# Good
async def search_flights(query: FlightQuery) -> list[Flight]:
    ...

# Bad - not explicit enough
async def search_flights(query: dict) -> list:
    ...
```

### Testing Requirements

**Every feature MUST have tests before merging:**
- **Unit tests**: Test individual functions and classes (100% coverage for business logic)
- **Functional tests**: Test API endpoints and integration flows (100% coverage for endpoints)
- **E2E tests**: Full request → response cycle with mocked external dependencies (TestClient hitting endpoints → mocked LLM/APIs)

**Coverage Goals:**
- Core business logic: 100%
- API endpoints: 100%
- Integration flows: 80%+
- Utilities: 80%+

**Test Workflow:**
1. Write implementation code first (not strict TDD)
2. Immediately write comprehensive tests covering:
   - Happy path
   - Error paths
   - Edge cases
   - Async behavior
3. Use pytest-asyncio for async tests
4. Mock external dependencies (LLM, APIs) for speed and reliability

**Acceptable During Exploration:**
- Writing code without tests to experiment
- BUT: Must add tests before considering feature "done"

### Code Quality Patterns to Enforce

**Always require:**
- Explicit return type annotations on all functions
- Docstrings for public APIs (Args, Returns, Raises format)
- Exception handling with specific exceptions (not bare `except`)
- Async functions (`async def`) for all I/O operations
- Pydantic models for request/response validation and core domain objects
- Type-safe dict accesses: `dict[str, str]` not `dict`

**Comment Style:**
- Comments explain **HOW** (only if needed for complex logic)
- **WHAT** belongs in docstrings
- Avoid obvious comments that restate code
- Use comments for non-obvious algorithmic decisions

**Flag aggressively:**
- Missing error handling in API endpoints
- Untyped external API responses
- Missing tests for error paths
- Synchronous I/O in async contexts (`requests` instead of `aiohttp`)
- Hardcoded configuration values (use env vars)
- Missing CORS configuration
- Blocking operations in async code

### SOLID Principles

**Pragmatic approach** - don't be overzealous, but mostly comply:
- **Single Responsibility**: Separate concerns (models, services, clients) into focused modules
- **Open/Closed**: Use inheritance and protocols for extensibility (FlightAPIClient abstract → Mock/Amadeus implementations)
- **Liskov Substitution**: Ensure subclasses can replace parent classes
- **Interface Segregation**: Keep protocols focused (don't add methods just because)
- **Dependency Inversion**: Depend on abstractions (Protocols/ABCs), not concrete implementations

**Prefer:**
- Small, reusable functions and classes
- Composition over inheritance where appropriate
- Factory patterns for object creation: `dict[str, Callable[..., T]]`
- Custom decorators for cross-cutting concerns (retry, logging, caching)
- Standalone utility functions in separate modules

### Dependency Injection Pattern

**Recommended approach:**
- **FastAPI Depends**: For external clients (API clients, database connections)
- **Service classes with constructor injection**: For business logic that needs state

**Example:**
```python
from fastapi import Depends

def get_flight_client() -> FlightAPIClient:
    """Dependency factory for flight API client."""
    return MockFlightAPIClient()  # Or AmadeusFlightAPIClient() in production

@app.post("/api/flights")
async def flights_endpoint(
    query: FlightQuery,
    client: FlightAPIClient = Depends(get_flight_client),
) -> list[Flight]:
    service = FlightService(client=client)
    return await service.search_flights(query)
```

**Benefits:**
- Clean testing (override dependencies in tests)
- Framework handles lifecycle management
- Clear separation between endpoints and business logic
- Easy to swap implementations (mock → real API)

### Async & Performance

**CRITICAL: Always use async/await for I/O:**
- **HTTP requests**: Use `aiohttp[speedups]` (NOT `requests`)
- **Database queries**: Use async drivers (future phases)
- **LLM calls**: Already async via LangChain
- **File I/O**: Use `aiofiles` if needed

**No threading/multiprocessing needed:**
- Python 3.13 with free-threaded mode available if really needed
- 95% of workload is I/O-intensive (perfect for asyncio)
- Keep it simple with single-threaded async event loop

### Error Handling & Retry Logic

**Exception Hierarchy:**
```python
class APIError(Exception):
    """Base API error."""
    retryable: bool = False

class APITimeoutError(APIError):
    retryable = True

class APIRateLimitError(APIError):
    retryable = True

class APIServerError(APIError):  # 5xx
    retryable = True

class APIClientError(APIError):  # 4xx
    retryable = False  # User error, don't retry
```

**Retry Strategy:**
- Use decorator pattern: `@retry_on_failure(max_retries=3, backoff_base=2.0)`
- Class-level configuration for all API client methods
- Exponential backoff for transient failures
- **Circuit breaker pattern**: Track failure rates, implement long retry timeout if API consistently down (prevent IP bans)
- **Rate limit handling**: Respect `Retry-After` headers, check API docs for rate limits before implementation

**LLM Tool Error Handling:**
- Return error message to LLM for correction if: "no flight options" or "incorrect date" (input validation errors)
- Fail entire request if: timeout, quota exceeded, API down (5xx errors)
- Always wrap and re-raise with context:
```python
try:
    return await external_api.search(...)
except HTTPError as e:
    raise FlightSearchError(f"Failed to search: {e}") from e
```

### External API Integration

**Wrapping Strategy:**
1. **LLM Provider (Ollama/Gemini/Cloud)**: 
   - No complex wrapper needed
   - Generic function/wrapper to allow switching providers
   - Configuration via UI (token input) or env vars
   - Support: Ollama (local), Gemini, OpenAI, Anthropic
2. **Flight APIs (Amadeus)**: 
   - Abstract base class: `FlightAPIClient`
   - Mock implementation: `MockFlightAPIClient` (Phase 3)
   - Real implementation: `AmadeusFlightAPIClient` (Phase 5)
3. **Future APIs (Hotels, Weather)**: 
   - Individual client classes, NOT a generic `ExternalAPIClient` Protocol
   - Each API has different endpoints, methods, quirks
   - No need for forced abstraction across unrelated APIs

### Commit Messages

**Use conventional commits format:**
- Format: `<type>: <short description>`
- Types: `feat`, `fix`, `test`, `docs`, `refactor`, `chore`, `style`
- Examples:
  - `feat: add flight search mock client`
  - `test: add e2e tests for flight search tool`
  - `refactor: extract retry logic into decorator`

## Communication Style

- **Explanations**: Detailed reasoning with examples, not brief bullets
- **Trade-offs**: Always discuss alternatives and implications
- **Learning moments**: Explain *why* something is problematic or better
- **Questions**: Always number questions for easy reference
- **Brevity**: Keep responses concise but complete
- **Non-trivial commands**: Explain purpose and impact before running

## Frontend Approach

- **Tech stack**: React + TypeScript + Chakra UI v3
- **Implementation**: Just implement and move on (lower learning priority)
- **Logic location**: ALL search/business logic in backend - frontend only handles:
  - User input and prompting
  - Displaying thinking/output asynchronously
  - Basic UI state management
- **Testing**: Basic tests, spaghetti code acceptable if functional
- **Major decisions**: Still present state management, routing choices for approval
- **Routes needed**: 
  - Login/auth (future)
  - Conversation history query (future)
  - Chat interface (current)

## Current Learning Goals

1. **Async programming patterns in Python** (async/await, asyncio, event loops)
2. **LangChain for LLM orchestration** (conversation memory, streaming, tool calling, agents)
3. **Modern Python tooling** (uv, ruff, mypy strict mode, pytest-asyncio)
4. **Production-ready FastAPI applications** (error handling, CORS, SSE, dependency injection)
5. **Integration testing with async code and mocked dependencies**
6. **External API integration** (aiohttp, retry logic, circuit breakers, rate limiting)
7. **Future**: DSPy exploration (comparing with LangChain)
8. **Future**: GraphQL API design and implementation

## Project Context

- **Implementation Plan**: Maintained in `PLAN.md`
  - High-level milestones (Phases)
  - Granular tasks with checkboxes
  - Track completion as we progress
  - Update after architecture decisions
- **Current Phase**: Phase 3 - Mock Flight Search Tool
- **Python Version**: 3.13 (free-threaded mode available if needed)
- **LLM**: Ollama (local, deepseek-r1:8b model) - future support for Gemini/Cloud providers

---

*This file is a living document. Update as we learn what works best.*
