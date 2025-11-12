"""Chat routes."""

import json
from collections.abc import AsyncGenerator

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.chat import chat_service
from app.domain.chat import ChatRequest

router = APIRouter()


@router.post("/api/chat")
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
