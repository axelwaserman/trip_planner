"""FastAPI application for Trip Planner."""

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import routes
from app.auth import routes as auth_routes
from app.auth.repository import PostgresUserRepository, UserRepository
from app.chat import (
    ChatService,
    ConversationRepository,
    MessageStore,
    PostgresConversationRepository,
    PostgresMessageStore,
)
from app.config import settings
from app.db.session import _async_sessionmaker, engine
from app.flights.amadeus_client import AmadeusFlightClient
from app.llm.factory import LLMProviderFactory
from app.llm.log_scrubbing import ApiKeyScrubber, install_log_scrubber, uninstall_log_scrubber
from app.tools.flight_client import FlightAPIClient, MockFlightAPIClient

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """Application lifespan - manage singleton resources.

    Startup:
        - Initialize flight API client.
        - Construct the per-app :class:`LLMProviderFactory` (D-03).
        - Construct the Phase 6 / Plan 06-04 split store collaborators —
          :class:`PostgresMessageStore` + :class:`PostgresConversationRepository`
          — plus the new :class:`PostgresUserRepository` (D-07; replaces the
          deleted env-backed user repository).
        - Initialize :class:`ChatService` with the split collaborators (D-05/D-06).
        - Stash ``db_engine``, ``message_store``, ``conversation_repo``,
          ``user_repo``, ``chat_service``, and ``llm_factory`` on ``app.state``.

    Shutdown:
        - Cleanup expired sessions (async since A1).
        - ``await engine.dispose()`` — release pooled connections cleanly so
          no DB connections leak between hot-reloads (T-06-04-02 mitigation).
    """
    # Startup
    # D-10: install API-key scrubber FIRST so any secret accidentally captured
    # by Settings() / factory init / lifespan-spawned tasks is redacted before
    # it reaches a handler's formatter. Phase 8's structlog migration replaces
    # this with a processor.
    log_scrubber: ApiKeyScrubber = install_log_scrubber()

    # Initialize flight client.
    # Phase 7 / Plan 07-05 (D-04, D-05): branch on amadeus_env + credential
    # presence. ``amadeus_env == "mock"`` and missing creds both fall back to
    # the mock client; only the missing-creds case logs WARN. Startup must
    # never fail because of missing creds (D-05) — a developer with no Amadeus
    # account still gets a working stack.
    if (
        settings.amadeus_env == "mock"
        or settings.amadeus_api_key is None
        or settings.amadeus_api_secret is None
    ):
        if settings.amadeus_env != "mock":
            logger.warning("AMADEUS_* creds missing — falling back to MockFlightAPIClient")
        flight_client: FlightAPIClient = MockFlightAPIClient(seed=42)
        flight_provider = "mock"
    else:
        # D-04: only two base URLs are constructable; the Literal type on
        # amadeus_env (config.py) keeps the input domain locked (T-07-01).
        base_url = (
            "https://test.api.amadeus.com"
            if settings.amadeus_env == "test"
            else "https://api.amadeus.com"
        )
        flight_client = AmadeusFlightClient(
            api_key=settings.amadeus_api_key.get_secret_value(),
            api_secret=settings.amadeus_api_secret.get_secret_value(),
            base_url=base_url,
        )
        flight_provider = "real"

    # Construct the per-app LLM factory; providers are built per-session.
    llm_factory = LLMProviderFactory(settings)

    # Phase 6 / Plan 06-04 (D-05/D-06): the Phase 5 single-store seam splits
    # into MessageStore (events) + ConversationRepository (meta-CRUD). Both
    # are Postgres-backed in production and share the lifespan's
    # _async_sessionmaker so they hit the same pool. Test code overrides
    # ``app.state.message_store`` / ``app.state.conversation_repo`` directly
    # for in-memory testing (Plan 06-04's integration tests do the wiring).
    message_store = PostgresMessageStore(_async_sessionmaker)
    conversation_repo = PostgresConversationRepository(_async_sessionmaker)

    chat_service = ChatService(
        flight_client=flight_client,
        factory=llm_factory,
        message_store=message_store,
        conversation_repo=conversation_repo,
    )

    # Store in app state
    app.state.db_engine = engine
    app.state.message_store = message_store
    app.state.conversation_repo = conversation_repo
    app.state.chat_service = chat_service
    # Phase 7 / Plan 07-05 (D-06): expose the flight client + provider choice.
    # ``flight_provider`` lets /health surface the active mode without
    # re-deriving the branch logic; ``flight_client`` lets Plan 06's
    # e2e_amadeus tests assert the constructed implementation directly.
    app.state.flight_client = flight_client
    app.state.flight_provider = flight_provider
    app.state.llm_factory = llm_factory

    # Phase 6 / Plan 06-04 (D-07): PostgresUserRepository is the sole impl.
    # The env-backed Phase 4 implementation was deleted; users are seeded via
    # ``just db-seed`` (Plan 06-06).
    app.state.user_repo = PostgresUserRepository(_async_sessionmaker)

    # D-05 + D-06: discovery cache + per-entry timestamps for TTL gating.
    # Populated by POST /api/providers/refresh and read by GET /api/providers.
    app.state.provider_models_cache = {}
    app.state.provider_models_cache_timestamps = {}

    yield

    # Shutdown: cleanup expired conversations (async since A1).
    cleaned_up = await chat_service.cleanup_expired_conversations(max_age_seconds=0)
    logger.info("Cleaned up %d conversations on shutdown", cleaned_up)

    # Phase 6 / Plan 06-04: dispose the engine so pooled connections close
    # cleanly between hot-reloads (T-06-04-02 mitigation; locked by
    # ``tests/integration/db/test_lifespan_engine_dispose.py``).
    await engine.dispose()

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
    allow_origins=settings.cors_allowed_origins,  # configurable via CORS_ALLOWED_ORIGINS env var
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Override the get_chat_service dependency to use app state
async def get_chat_service_override(request: Request) -> ChatService:
    """Get the chat service from app state."""
    return request.app.state.chat_service  # type: ignore[no-any-return]


async def get_llm_factory_override(request: Request) -> LLMProviderFactory:
    """Get the LLM factory from app state (Plan 04.5-06b — D-06 refresh)."""
    return request.app.state.llm_factory  # type: ignore[no-any-return]


async def get_user_repository_override(request: Request) -> UserRepository:
    """Get the UserRepository from app state (Phase 4.9-02 DI wiring)."""
    return request.app.state.user_repo  # type: ignore[no-any-return]


async def get_message_store_override(request: Request) -> MessageStore:
    """Get the MessageStore from app state (Plan 06-04 D-05 wiring)."""
    return request.app.state.message_store  # type: ignore[no-any-return]


async def get_conversation_repo_override(request: Request) -> ConversationRepository:
    """Get the ConversationRepository from app state (Plan 06-04 D-06 wiring)."""
    return request.app.state.conversation_repo  # type: ignore[no-any-return]


app.dependency_overrides[routes.get_chat_service] = get_chat_service_override
app.dependency_overrides[routes.get_llm_factory] = get_llm_factory_override
app.dependency_overrides[auth_routes.get_user_repository] = get_user_repository_override
app.dependency_overrides[routes.get_message_store] = get_message_store_override
app.dependency_overrides[routes.get_conversation_repo] = get_conversation_repo_override

# Include router
app.include_router(routes.router)
app.include_router(auth_routes.router, prefix="/api/auth")
