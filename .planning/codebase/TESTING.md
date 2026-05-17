# Testing

> Mapped: 2026-04-27

## Framework

- **Backend**: pytest with pytest-asyncio
- **Frontend**: No test framework configured yet

## Configuration

Defined in `backend/pyproject.toml`:

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
pythonpath = ["."]
addopts = "-m 'not slow'"
```

## Test Categories

| Marker | Purpose | Run Command |
|--------|---------|-------------|
| `unit` | Pure unit tests, no external deps | `pytest -m unit` |
| `integration` | Mocked external deps, real FastAPI | `pytest -m integration` |
| `e2e` / `slow` | Real LLM calls, full flow | `pytest -m e2e` |

Default run skips `slow` tests via `addopts`.

## Test Structure

```
backend/tests/
├── conftest.py                                    # Shared fixtures
├── fixtures/                                      # Test data
├── unit/
│   ├── test_exceptions.py                         # Exception hierarchy
│   ├── test_flight_models.py                      # Pydantic model validation
│   ├── test_mock_client.py                        # MockFlightAPIClient
│   └── test_retry.py                              # Retry decorator (async)
├── integration/
│   ├── test_chat.py                               # Chat endpoint with mocked LLM
│   ├── test_health.py                             # Health endpoint
│   └── test_chat_service_mocked_llm.py.skip       # Disabled mocked LLM test
└── e2e/
    ├── test_e2e.py                                # Full flow with real LLM
    └── test_e2e_manual.py                         # Manual e2e tests
```

## Fixtures

Shared fixtures in `backend/tests/conftest.py`:

- `mock_flight_client()` - `MockFlightAPIClient` with fixed seed (42) for reproducibility
- `mock_llm_provider()` - `MagicMock(spec=BaseChatModel)` with `bind_tools` returning self

## Patterns

### Unit Tests
- AAA pattern (Arrange-Act-Assert)
- `@pytest.mark.asyncio` for async tests
- Autouse fixtures for state reset between tests (e.g., `reset_function_state` in `test_retry.py`)
- Direct function testing, no HTTP layer

### Integration Tests
- `TestClient(app)` from FastAPI for HTTP-level tests
- `unittest.mock.patch` for mocking service methods
- Session creation via `POST /api/chat/session` before chat tests

### E2E Tests
- `pytestmark = [pytest.mark.slow, pytest.mark.e2e]` on module
- Real LLM calls (requires running Ollama)
- SSE stream parsing helper `parse_sse_stream()`
- Multi-turn conversation tests
- Error handling tests (invalid IATA codes, bad dates)

## Mocking Approach

- `MockFlightAPIClient` - built-in mock in production code (`backend/app/tools/flight_client.py`) with seeded random data
- `MagicMock(spec=BaseChatModel)` - for LLM in unit tests
- `unittest.mock.patch` - for integration tests patching service methods
- No database mocking needed (in-memory state only)

## Coverage

- No coverage tool configured in `pyproject.toml`
- No CI pipeline observed
- Missing coverage: frontend has zero tests
- Skipped test files: `test_chat_service_mocked_llm.py.skip` (renamed to disable)

## Gaps

- No frontend tests at all (no Vitest, no Playwright)
- No coverage reporting configured
- No CI/CD pipeline
- Some integration tests have inconsistent status code expectations (201 vs 200 for session creation)
- E2E tests depend on running Ollama instance
