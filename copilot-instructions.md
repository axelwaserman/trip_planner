# Copilot Instructions for Trip Planner Project

## Project Overview
AI-powered trip planner: FastAPI + async + LangChain 1.0 for backend, React + TypeScript + Chakra UI for frontend.

**Docs**: [backend/README.md](backend/README.md) | [PLAN.md](PLAN.md)

---

## Development Workflow

### Two-Pass Development Approach
1. **Implementation Pass**: Write clean, working code that passes tests
   - Focus on functionality and correctness
   - Ensure full typing and test coverage
   - Run all checks: `just check`
   - Commit at each checkpoint
2. **Review Pass**: When you ask "please review and refactor"
   - Provide PR-style feedback on code quality
   - Identify refactoring opportunities
   - Suggest architectural improvements
   - Point out edge cases or missing tests

### Checkpoint Protocol
- **Frequency**: 3-5 checkpoints per phase
- **Process**: 
  1. Complete checkpoint work
  2. Run `just test` and `just check`
  3. Commit with conventional commit message
  4. Brief status update: done + next
  5. Wait for approval before continuing
- **Purpose**: Enable review, course correction, clean git history

### Architecture Decision Process

**Always ask before implementing:**
- New API endpoints, external integrations, state management changes
- Major refactoring (>100 lines) or data structure design

**Present:** Data structures, class hierarchy, 2-3 approaches with trade-offs, recommendation

**No discussion needed:** Bug fixes, tests, docs, minor refactoring (<50 lines), frontend styling

---

## Your Role: Critical Sparring Partner

- **Number all questions** for easy reference
- **Challenge:** Security, tech debt, missing errors, performance (N+1, blocking I/O), type safety, speed-over-quality shortcuts
- **Don't challenge:** Solid approaches, preferences, exploration code, minor optimizations (<10% impact)
- **Method:** Ask numbered questions → Share reasoning with examples → Present alternatives with trade-offs → Let me decide, then implement fully

### Implementation Protocol
**BEFORE writing code:**
1. **Search official documentation** for current library patterns (LangChain 1.0, FastAPI best practices)
2. **Always inspect source code** of external dependencies before implementing
3. **Balance speed vs quality:** Favor maintainability, build for production, don't over-engineer (YAGNI), question: "Will this create tech debt in 2 phases?"

---

## Technical Standards

### Mandatory Tooling (NON-NEGOTIABLE)
- **`uv`** for ALL package management (NEVER `pip`, `poetry`, or `conda`)
- **`mypy`** strict mode for type checking (NO `type: ignore` without explicit justification)
- **`pytest`** with `pytest-asyncio` for testing (NO other test frameworks)
- **`ruff`** for linting and formatting (consolidated config in `pyproject.toml`)

### Type Safety & Testing
**Type annotations:**
- Explicit return types on all functions
- No bare `dict` or `list` - always specify: `dict[str, str]`, `list[Flight]`
- Custom types only for complex nested structures
- Validate with Pydantic, not NewType

**Example:**
```python
# Good
async def search_flights(query: FlightQuery) -> list[Flight]:
    ...

# Bad
async def search_flights(query: dict) -> list:
    ...
```

**Tests required before merging:**
- **Unit tests**: Individual functions/classes (100% coverage for business logic)
- **Functional tests**: API endpoints (100% coverage)
- **E2E tests**: Full request → response with mocked external deps (80%+)

Write implementation first, then comprehensive tests (happy path + errors + edge cases).

### Code Structure & Patterns

**Pattern Names:**
- **Data Model Pattern**: Pydantic models in `models.py` - data structures only, no business logic except validators/getters/setters
- **Abstract Client Pattern**: Stateful/complex logic uses OOP - generic ABC with multiple concrete implementations
- **Functional Service Pattern**: Stateless/simple logic uses functions with decorators if needed
- **Dependency Injection Pattern**: FastAPI `Depends()` for clean testing and lifecycle management

**Code quality checklist:**
- ✓ Explicit return type annotations
- ✓ Docstrings for public APIs (Args, Returns, Raises)
- ✓ Specific exceptions (not bare `except`)
- ✓ **Always `async def` for ALL I/O operations**
- ✓ Pydantic models for validation
- ✓ Type-safe collections: `dict[str, str]`, `list[Flight]`
- ✗ Missing error handling in endpoints
- ✗ Untyped external API responses
- ✗ Missing tests for error paths
- ✗ Sync I/O in async contexts
- ✗ Hardcoded config values
- ✗ Blocking operations in async code

**Comments philosophy:**
- Never comment what something does, only why if necessary

**Async I/O requirements:**
- HTTP: `aiohttp[speedups]` (NOT `requests`)
- Database: async drivers (future)
- LLM: async via LangChain
- File I/O: `aiofiles` if needed
- No threading/multiprocessing - Python 3.13 async event loop handles everything

**Dependency Injection example:**
```python
from fastapi import Depends

def get_flight_client() -> FlightAPIClient:
    return MockFlightAPIClient()

@app.post("/api/flights")
async def endpoint(
    query: FlightQuery,
    client: FlightAPIClient = Depends(get_flight_client),
) -> list[Flight]:
    service = FlightService(client=client)
    return await service.search_flights(query)
```

---

## Communication Style

- **Explanations**: Detailed reasoning with examples
- **Trade-offs**: Always discuss alternatives
- **Questions**: Always number for easy reference
- **Brevity**: Concise but complete
- **Commands**: Explain non-trivial purposes
- **Commits**: Use conventional commits (`feat:`, `fix:`, `test:`, `docs:`, `refactor:`, `chore:`)
