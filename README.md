# Trip Planner

AI-powered trip planning assistant with conversational interface and real-time travel data integration.

## Project Structure

```
trip_planner/
├── backend/          # FastAPI backend
│   ├── app/         # Application code
│   ├── tests/       # Tests
│   └── ...
├── frontend/         # React + TypeScript frontend
│   ├── src/         # Frontend code
│   └── ...
├── PLAN.md          # Implementation roadmap
└── copilot-instructions.md  # Development guidelines
```

## Tech Stack

### Backend
- **FastAPI** - Modern async Python web framework
- **LangChain** - LLM orchestration and agent framework
- **Ollama** - Local LLM (gpt-oss20b)
- **Python 3.13** - Latest Python with enhanced type system
- **uv** - Fast Python package manager
- **pytest** - Testing framework
- **ruff** - Linting and formatting
- **mypy** - Static type checking

### Frontend
- **React 18** - UI framework
- **TypeScript** - Type-safe JavaScript
- **Vite** - Lightning-fast build tool
- **Chakra UI v3** - Component library
- **Framer Motion** - Animations

## Quick Start

### Prerequisites

- Python 3.13+
- Node.js 20+
- [uv](https://github.com/astral-sh/uv) - Install: `curl -LsSf https://astral.sh/uv/install.sh | sh`
- [Ollama](https://ollama.ai/) with gpt-oss20b model

### Backend Setup

```bash
cd backend

# Install dependencies
uv sync --dev

# Configure environment
cp .env.example .env

# Run server
uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

# Run tests
uv run pytest

# Lint and type check
uv run ruff check .
uv run mypy src/
```

Backend runs on http://localhost:8000

### Frontend Setup

```bash
cd frontend

# Install dependencies
npm install

# Run dev server
npm run dev
```

Frontend runs on http://localhost:5173

API calls to `/api/*` are automatically proxied to the backend.

## Development Workflow

1. **Start Ollama** (if not running):
   ```bash
   ollama serve
   ```

2. **Run backend** (Terminal 1):
   ```bash
   cd backend && uv run uvicorn app.main:app --reload
   ```

3. **Run frontend** (Terminal 2):
   ```bash
   cd frontend && npm run dev
   ```

4. **Open browser**: http://localhost:5173

## Features (Roadmap)

- [x] Project structure and tooling
- [ ] Chat interface with conversational AI
- [ ] LangChain agent with tool calling
- [ ] Mock flight search tool
- [ ] Real Amadeus API integration
- [ ] Database persistence (future)
- [ ] GraphQL API layer (future)
- [ ] Additional tools: hotels, restaurants, weather (future)

## Documentation

- [Implementation Plan](./PLAN.md) - Detailed roadmap with phases
- [Copilot Instructions](./copilot-instructions.md) - Development guidelines
- [Backend README](./backend/README.md) - Backend-specific docs
- [Frontend README](./frontend/README.md) - Frontend-specific docs

## Contributing

This is a learning project. See `copilot-instructions.md` for development philosophy and code quality standards.

## License

Private project
