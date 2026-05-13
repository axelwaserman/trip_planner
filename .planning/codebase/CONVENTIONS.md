# Coding Conventions

**Analysis Date:** 2026-04-27

## Project Structure

This is a monorepo with two top-level applications:
- `backend/` -- Python FastAPI backend
- `frontend/` -- TypeScript React frontend (Vite + Chakra UI v3)

Each follows its own conventions. Shared conventions are noted where applicable.

---

## Backend (Python)

### Naming Patterns

**Files:**
- All lowercase with underscores: `flight_client.py`, `flight_search.py`
- Modules use `__init__.py` (even if empty) for package recognition
- Test files prefixed with `test_`: `test_retry.py`, `test_flight_models.py`

**Functions:**
- `snake_case` for all functions: `search_flights`, `get_session_history`, `cleanup_expired_sessions`
- Async functions use `async def` and follow the same naming pattern
- Private helpers prefixed with underscore: `_generate_flights`, `_apply_filters`, `_sort_flights`

**Classes:**
- `PascalCase`: `FlightAPIClient`, `MockFlightAPIClient`, `ChatService`, `Settings`
- Exception classes use `Error` suffix: `APIError`, `APITimeoutError`, `FlightSearchError`

**Variables:**
- `snake_case` for locals and instance attributes: `flight_client`, `session_id`, `departure_date`
- Module-level singletons in lowercase: `settings = Settings()` (`backend/app/config.py`)
- Type aliases in `PascalCase`: `BookingClass`, `SortBy` (`backend/app/models.py`)

**Constants:**
- `UPPER_SNAKE_CASE` for class-level constants: `CARRIERS` in `MockFlightAPIClient` (`backend/app/tools/flight_client.py`)

### Code Style

**Formatting:**
- Ruff formatter (replaces black/isort)
- Line length: 100 characters
- Config: `backend/pyproject.toml` `[tool.ruff]` section
- Target Python version: 3.13

**Linting:**
- Ruff with rule sets: E, W, F, I, UP, B, C4, N, SIM, TCH
- `E501` (line too long) ignored (handled by formatter)
- isort integrated via Ruff with `known-first-party = ["app"]`
- Tests allow `assert` statements (`S101` ignored for `tests/**`)
- Config: `backend/pyproject.toml` `[tool.ruff.lint]` section

**Type Checking:**
- mypy in strict mode
- Config: `backend/pyproject.toml` `[tool.mypy]` section
- `disallow_untyped_defs = true`, `warn_return_any = true`
- All function signatures require type annotations

### Import Organization

**Order (enforced by Ruff isort):**
1. Standard library imports (`datetime`, `uuid`, `re`, `typing`)
2. Third-party imports (`fastapi`, `pydantic`, `langchain_core`)
3. First-party imports (prefixed `app.`): `from app.models import ...`

**Style:**
- Prefer `from X import Y` over `import X`
- Use `from __future__ import annotations` is NOT used (Python 3.13 native syntax)
- Use `str | None` union syntax (Python 3.10+), never `Optional[str]`
- Use `TYPE_CHECKING` guard for circular imports (`backend/app/tools/flight_search.py` line 6)

```python
# Example from backend/app/tools/flight_search.py
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.tools.flight_client import FlightAPIClient
```

### Error Handling

**Exception Hierarchy:**
- Base: `TripPlannerError(Exception)` (`backend/app/exceptions.py`)
- API errors use `@dataclass` with `retryable` flag
- Concrete exceptions: `APITimeoutError`, `APIRateLimitError`, `APIServerError`, `APIClientError`
- Domain: `FlightSearchError(TripPlannerError)`

**Pattern - Never raise to LLM:**
In tool functions, catch all exceptions and return error strings rather than raising:
```python
# backend/app/tools/flight_search.py
except FlightSearchError as e:
    return f"Flight search error: {e}"
except Exception as e:
    return f"Unexpected error during flight search: {e}"
```

**Pattern - HTTPException for API routes:**
Use `fastapi.HTTPException` with specific status codes:
```python
# backend/app/api/routes/routes.py
raise HTTPException(
    status_code=status.HTTP_404_NOT_FOUND,
    detail=f"Session {session_id} not found",
) from err
```

**Pattern - SSE error wrapping:**
Streaming endpoints wrap errors in `StreamEvent` objects rather than HTTP errors:
```python
# backend/app/api/routes/routes.py
except Exception as e:
    error_event = StreamEvent(
        chunk=f"An error occurred: {str(e)}",
        session_id=request.session_id,
        type="content",
    )
    yield f"data: {error_event.model_dump_json()}\n\n"
```

### Pydantic Model Patterns

**Schema design (all in `backend/app/models.py`):**
- Use `Field(...)` with `description`, `min_length`, `max_length`, `ge`, `le` constraints
- Use `@field_validator` for custom validation (e.g., IATA code normalization)
- Use `@model_validator(mode="after")` for cross-field validation
- Type aliases via `Literal`: `BookingClass = Literal["economy", "premium_economy", "business", "first"]`
- Use `Self` return type for model validators

**Settings pattern (`backend/app/config.py`):**
- Inherit from `pydantic_settings.BaseSettings`
- Use `SettingsConfigDict(env_file=".env", extra="ignore")`
- Provide defaults for all settings
- Instantiate module-level singleton: `settings = Settings()`

### Dependency Injection

**FastAPI DI pattern:**
- Define placeholder dependency functions in route modules
- Override with real implementations via `app.dependency_overrides` in `backend/app/api/main.py`
- Use `Depends()` in route function signatures

```python
# backend/app/api/routes/routes.py
async def get_chat_service() -> ChatService:
    raise RuntimeError("ChatService not configured in app state")

# backend/app/api/main.py
app.dependency_overrides[routes.get_chat_service] = get_chat_service_override
```

### Docstrings

Use Google-style docstrings on all public functions and classes:
```python
def search(
    self,
    query: FlightQuery,
    sort_by: SortBy = "price",
) -> list[Flight]:
    """Search for flights with filtering and sorting.

    Args:
        query: Flight search parameters
        sort_by: Sort criteria (price, duration, or departure time)

    Returns:
        List of flights matching criteria, sorted and paginated
    """
```

### Abstract Base Classes

Use `abc.ABC` with `@abstractmethod` for client interfaces:
```python
# backend/app/tools/flight_client.py
class FlightAPIClient(ABC):
    @abstractmethod
    async def search(self, query: FlightQuery, ...) -> list[Flight]:
        ...
```

### Logging

- Use `logging.getLogger(__name__)` pattern (`backend/app/tools/retry.py`)
- Use f-string log messages (note: Ruff does not enforce lazy formatting)
- `print()` used in lifespan shutdown (should be replaced with logger)

---

## Frontend (TypeScript/React)

### Naming Patterns

**Files:**
- Components: `PascalCase.tsx`: `ChatInterface.tsx`, `ProviderSelector.tsx`, `ThinkingCard.tsx`
- Entry points: `main.tsx`, `App.tsx`
- CSS files: `kebab-case.css`: `App.css`, `index.css`

**Components:**
- `PascalCase` function components: `ChatInterface`, `ProviderSelector`, `ThinkingCard`
- Exported as named exports: `export function ChatInterface() {}`
- No `React.FC` usage

**Interfaces/Types:**
- `PascalCase` with descriptive suffix: `ToolCallMetadata`, `ToolResultMetadata`, `ProviderSelectorProps`
- Props interfaces use `Props` suffix: `ThinkingCardProps`, `ToolExecutionCardProps`
- Type aliases for string unions: `type MessageType = 'user' | 'assistant' | 'tool_execution' | 'thinking'`

**Variables/Functions:**
- `camelCase`: `sendMessage`, `handleSubmit`, `scrollToBottom`
- Event handlers prefixed with `handle`: `handleProviderChange`, `handleModelChange`, `handleKeyDown`
- State variables use descriptive names: `isLoading`, `isExpanded`, `sessionId`

### Code Style

**Formatting:**
- No Prettier configured (relies on IDE defaults)
- TypeScript strict mode enabled (`frontend/tsconfig.app.json`)
- `noUnusedLocals`, `noUnusedParameters` enabled

**Linting:**
- ESLint 9 flat config (`frontend/eslint.config.js`)
- Extends: `js.configs.recommended`, `tseslint.configs.recommended`
- Plugins: `eslint-plugin-react-hooks`, `eslint-plugin-react-refresh`
- TypeScript files only: `**/*.{ts,tsx}`

### Import Organization

**Order (no enforced tooling):**
1. Third-party library imports (`@chakra-ui/react`, `react`, `react-markdown`)
2. Relative imports (`./ToolExecutionCard`, `./ThinkingCard`)

**Style:**
- Named imports for Chakra components: `import { Box, Button, Flex } from '@chakra-ui/react'`
- Type-only imports with `import type`: `import type { FormEvent, KeyboardEvent } from 'react'`
- Chakra v3 compound component dot notation: `Collapsible.Root`, `Collapsible.Trigger`

### Component Design

**Pattern - Props with interfaces:**
```tsx
// frontend/src/components/ThinkingCard.tsx
interface ThinkingCardProps {
  content: string
}

export function ThinkingCard({ content }: ThinkingCardProps) { ... }
```

**Pattern - Chakra UI v3 style props:**
- Use Chakra style props directly: `bg="gray.50"`, `rounded="lg"`, `p={4}`
- Responsive values not yet used (single breakpoint UI)
- Compound components: `Collapsible.Root`, `Collapsible.Trigger`, `Collapsible.Content`

**Pattern - State management:**
- `useState` for all local state (no global state library)
- `useRef` for DOM references (scroll-to-bottom)
- `useEffect` for initialization and side effects
- `localStorage` for persisting provider selection

**Pattern - Duplicate interfaces:**
- `ToolCallMetadata` and `ToolResultMetadata` are duplicated across `ChatInterface.tsx`, `ToolExecutionCard.tsx`, `ToolCallCard.tsx`, and `ToolResultCard.tsx`
- No shared types file exists

### CSS Conventions

- Chakra UI style props preferred over custom CSS
- `App.css` and `index.css` are Vite template defaults (largely unused)
- No custom CSS classes for application components
- No Tailwind or CSS modules

### Error Handling

**Pattern - Try/catch with user-friendly messages:**
```tsx
// frontend/src/components/ChatInterface.tsx
catch (error) {
  console.error('Chat error:', error)
  setMessages((prev) => [
    ...prev,
    { role: 'assistant', content: 'Sorry, I encountered an error. Please try again.' },
  ])
}
```

### Console Usage

- `console.log` and `console.error` used for debugging in `ChatInterface.tsx` (lines 69, 109, 119, 148, 266)
- These should be removed or replaced with a proper logging approach for production

---

## Skill-Defined Conventions

### Chakra UI v3 (`.claude/skills/chakra-ui/SKILL.md`)

- Use compound components with dot notation: `Dialog.Root`, `Dialog.Content`
- Use `colorPalette` prop (not `colorScheme`) for Chakra v3
- Wrap overlays in `Portal`
- Use `Field.Root` for form fields with `Field.Label`, `Field.ErrorText`
- Use `createSystem` / `defineConfig` for custom theming
- Use semantic tokens (`brand.solid`) over raw color values

### FastAPI (`.claude/skills/fastapi/SKILL.md`)

- Separate Pydantic schemas from SQLAlchemy models
- Use `Annotated` for dependency aliases
- Use service layer pattern (business logic out of routes)
- Use `str | None` syntax (Python 3.10+), never `Optional`
- Use `lifespan` context manager (not `@app.on_event`)
- Return proper status codes: 201 for create, 204 for delete

---

*Convention analysis: 2026-04-27*
