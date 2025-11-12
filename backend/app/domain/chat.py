"""Pydantic models for API requests and responses."""

from datetime import datetime
from enum import Enum
from typing import Any

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
    started_at: datetime = Field(..., description="When tool execution started")
    status: str = Field(default="executing", description="Tool execution status")


class ToolResultMetadata(BaseModel):
    """Metadata for tool result messages."""

    tool_name: str = Field(..., description="Name of the tool that was executed")
    summary: str = Field(..., description="Brief summary of the result (2-3 lines)")
    full_result: str = Field(..., description="Complete result in markdown format")
    status: str = Field(..., description="Result status: complete or error")
    completed_at: datetime = Field(..., description="When tool execution completed")
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

