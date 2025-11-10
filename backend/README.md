# Trip Planner Backend

AI-powered trip planning assistant API built with FastAPI.

## Prerequisites

- Python 3.13+
- [uv](https://github.com/astral-sh/uv) for dependency management
- [Ollama](https://ollama.ai/) with gpt-oss20b model

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
   
   # Verify gpt-oss20b is available
   ollama list
   ```

## Development

**Run the server:**
```bash
uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

**Run tests:**
```bash
uv run pytest
```

**Lint code:**
```bash
uv run ruff check .
uv run ruff format .
```

**Type check:**
```bash
uv run mypy src/
```

## API Documentation

Once running, visit:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## Project Structure

```
backend/
├── src/
│   └── app/
│       ├── __init__.py
│       └── main.py          # FastAPI application
├── tests/
│   └── __init__.py
├── pyproject.toml           # Dependencies & config
├── ruff.toml               # Linting configuration
├── .python-version         # Python version (3.13)
└── .env.example            # Environment template
```
