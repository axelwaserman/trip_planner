"""FastAPI application for Trip Planner."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import auth, routes
from app.chat import ChatService
from app.config import Settings
from app.llm.factory import LLMProviderFactory
from app.llm.log_scrubbing import ApiKeyScrubber, install_log_scrubber, uninstall_log_scrubber
from app.tools.flight_client import MockFlightAPIClient
from app.tools.flight_search import search_flights


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """Application lifespan - manage singleton resources.

    Startup:
        - Initialize flight API client.
        - Construct the per-app :class:`LLMProviderFactory` (D-03 — replaces the
          4.2 startup-time chat-model construction; providers are built
          per-session inside :meth:`ChatService.create_session`).
        - Initialize :class:`ChatService` with the factory.
        - Inject ``flight_client`` into the ``search_flights`` tool.
        - Stash both ``chat_service`` and ``llm_factory`` on ``app.state``.

    Shutdown:
        - Cleanup expired sessions.
    """
    # Startup
    # D-10: install API-key scrubber FIRST so any secret accidentally captured
    # by Settings() / factory init / lifespan-spawned tasks is redacted before
    # it reaches a handler's formatter. Phase 8's structlog migration replaces
    # this with a processor.
    log_scrubber: ApiKeyScrubber = install_log_scrubber()

    settings = Settings()

    # Initialize flight client
    flight_client = MockFlightAPIClient(seed=42)

    # Construct the per-app LLM factory; providers are built per-session.
    llm_factory = LLMProviderFactory(settings)

    # Inject flight_client into search_flights tool
    search_flights._flight_client = flight_client  # type: ignore[attr-defined]

    # Initialize chat service with the factory (D-03 — no singleton bound LLM).
    chat_service = ChatService(
        flight_client=flight_client,
        factory=llm_factory,
    )

    # Store in app state
    app.state.chat_service = chat_service
    app.state.llm_factory = llm_factory

    yield

    # Shutdown: cleanup expired sessions
    cleaned_up = chat_service.cleanup_expired_sessions(max_age_seconds=0)
    print(f"Cleaned up {cleaned_up} sessions on shutdown")

    # D-10: best-effort filter cleanup. Failure to remove must not raise on shutdown.
    uninstall_log_scrubber(log_scrubber)


app = FastAPI(
    title="Trip Planner API",
    description="AI-powered trip planning assistant",
    version="0.1.0",
    lifespan=lifespan,
)

# Configure CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # Vite dev server
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Override the get_chat_service dependency to use app state
async def get_chat_service_override(request: Request) -> ChatService:
    """Get the chat service from app state."""
    return request.app.state.chat_service  # type: ignore[no-any-return]


app.dependency_overrides[routes.get_chat_service] = get_chat_service_override

# Include router
app.include_router(routes.router)
app.include_router(auth.router, prefix="/api/auth")
