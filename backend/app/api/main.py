"""FastAPI application for Trip Planner."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from langchain.chat_models import init_chat_model

from app.chat import ChatService
from app.config import Settings
from app.api.routes import auth, routes 
from app.tools.flight_client import MockFlightAPIClient
from app.tools.flight_search import search_flights


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """Application lifespan - manage singleton resources.

    Startup:
        - Initialize flight API client
        - Initialize LLM with init_chat_model()
        - Initialize ChatService with dependencies
        - Inject flight_client into search_flights tool

    Shutdown:
        - Cleanup expired sessions
    """
    # Startup
    settings = Settings()

    # Initialize flight client
    flight_client = MockFlightAPIClient(seed=42)

    # Initialize LLM using init_chat_model with reasoning enabled
    llm = init_chat_model(
        model=settings.ollama_model,
        model_provider="ollama",
        base_url=settings.ollama_base_url,
        reasoning=True,  # Enable reasoning/thinking tokens for supported models
    )

    # Inject flight_client into search_flights tool
    search_flights._flight_client = flight_client

    # Initialize chat service
    chat_service = ChatService(
        flight_client=flight_client,
        llm=llm,
    )

    # Store in app state
    app.state.chat_service = chat_service

    yield

    # Shutdown: cleanup expired sessions
    cleaned_up = chat_service.cleanup_expired_sessions(max_age_seconds=0)
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


# Override the get_chat_service dependency to use app state
async def get_chat_service_override(request: Request) -> ChatService:
    """Get the chat service from app state."""
    return request.app.state.chat_service


app.dependency_overrides[routes.get_chat_service] = get_chat_service_override

# Include router
app.include_router(routes.router)
app.include_router(auth.router)