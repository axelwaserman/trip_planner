"""FastAPI application for Trip Planner."""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import chat, flights, health
from app.infrastructure.clients.mock import MockFlightAPIClient
from app.infrastructure.storage.session import InMemorySessionStore


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan - manage singleton resources.

    Startup:
        - Initialize flight API client
        - Initialize session store with TTL

    Shutdown:
        - Cleanup all sessions
    """
    # Startup
    app.state.flight_client = MockFlightAPIClient(seed=42)
    app.state.session_store = InMemorySessionStore(default_ttl_seconds=3600)  # 1 hour TTL

    yield

    # Shutdown: cleanup all sessions
    cleaned_up = await app.state.session_store.cleanup_expired(max_age_seconds=0)
    print(f"Cleaned up {cleaned_up} sessions on shutdown")


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

# Include routers
app.include_router(health.router, tags=["health"])
app.include_router(chat.router, tags=["chat"])
app.include_router(flights.router, prefix="/api", tags=["flights"])
