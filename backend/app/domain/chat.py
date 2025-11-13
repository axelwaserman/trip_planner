"""Pydantic models for API requests and responses."""

from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


class MessageType(str, Enum):
    """Types of messages in chat conversation."""

    USER = "user"
    ASSISTANT = "assistant"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"


class ToolCallMetadata(BaseModel):
    """Metadata for tool call messages."""

    tool_name: str = Field(..., description="Name of the tool being called")
    arguments: dict[str, Any] = Field(..., description="Arguments passed to the tool")
    started_at: float = Field(..., description="Unix timestamp when tool execution started")
    status: str = Field(default="running", description="Tool execution status")


class ToolResultMetadata(BaseModel):
    """Metadata for tool result messages."""

    summary: str = Field(..., description="Brief summary of the result (2-3 lines)")
    full_result: str = Field(..., description="Complete result in markdown format")
    status: str = Field(..., description="Result status: success or error")
    elapsed_ms: int = Field(..., description="Execution time in milliseconds")


class ChatRequest(BaseModel):
    """Request model for chat endpoint."""

    message: str = Field(..., min_length=1, description="User message to send to the agent")
    session_id: str | None = Field(
        default=None, description="Optional session ID for conversation continuity"
    )


class ChatResponse(BaseModel):
    """Response model for chat endpoint."""

    response: str = Field(..., description="Agent's response message")
    session_id: str = Field(..., description="Session ID for this conversation")


class StreamEvent(BaseModel):
    """Event emitted during chat streaming.
    
    Used for Server-Sent Events (SSE) to stream chat responses with tool visibility.
    """

    chunk: str = Field(default="", description="Content chunk or empty string for tool events")
    session_id: str = Field(..., description="Session ID for this conversation")
    event_type: Literal["content", "tool_call", "tool_result"] = Field(
        ..., description="Type of event being streamed"
    )
    metadata: ToolCallMetadata | ToolResultMetadata | None = Field(
        default=None, description="Event-specific metadata (typed Pydantic model)"
    )

