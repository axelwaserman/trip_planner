"""FastAPI application for Trip Planner."""

import json
from collections.abc import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from app.chat import chat_service
from app.models.chat import ChatRequest

app = FastAPI(
    title="Trip Planner API",
    description="AI-powered trip planning assistant",
    version="0.1.0",
)

# Configure CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # Vite dev server
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root() -> dict[str, str]:
    """Root endpoint."""
    return {"message": "Trip Planner API"}


@app.get("/api/health")
async def health() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "healthy"}


@app.post("/api/chat")
async def chat(request: ChatRequest) -> StreamingResponse:
    """Streaming chat endpoint that returns Server-Sent Events.

    Args:
        request: Chat request with message and optional session_id

    Returns:
        StreamingResponse with SSE chunks
    """

    async def event_generator() -> AsyncGenerator[str]:
        """Generate Server-Sent Events for streaming response."""
        try:
            session_id = None
            async for chunk, sid in chat_service.chat_stream(request.message, request.session_id):
                session_id = sid
                # Send chunk as SSE
                data = json.dumps({"chunk": chunk, "session_id": session_id})
                yield f"data: {data}\n\n"

            # Send done event
            yield f"data: {json.dumps({'done': True, 'session_id': session_id})}\n\n"
        except Exception as e:
            # Send error event
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        },
    )
