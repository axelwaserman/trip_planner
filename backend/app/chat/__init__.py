"""Chat domain package (Phase 4.7 → Phase 6).

Houses ``ChatService`` (moved from ``app/chat.py`` in Phase 4.7) and the
discriminated-union event model hierarchy that replaces the monolithic
``StreamEvent`` class. Phase 5 added the per-turn :class:`ChatDeps` DTO
(D-05) and the original :class:`ConversationStore` ABC (D-08, D-11) that
PydanticAI's ``Agent`` consumes. Phase 6 / Plan 06-03+04 split that ABC
into :class:`MessageStore` (events) and :class:`ConversationRepository`
(meta-CRUD) per CONTEXT.md D-05/D-06; the legacy ``ConversationStore`` was
deleted alongside the ChatService rewire (Plan 06-04).
"""

from app.chat.deps import ChatDeps
from app.chat.models import (
    ContentEvent,
    ErrorCode,
    ErrorEvent,
    StreamEvent,
    ThinkingEvent,
    ToolCallEvent,
    ToolResultEvent,
)
from app.chat.repository import (
    ConversationRecord,
    ConversationRepository,
    InMemoryConversationRepository,
    PostgresConversationRepository,
)
from app.chat.service import ChatService
from app.chat.store import (
    ConversationConcurrentAppendError,
    InMemoryMessageStore,
    MessageStore,
    PostgresMessageStore,
)

__all__ = [
    "ChatDeps",
    "ChatService",
    "ContentEvent",
    "ConversationConcurrentAppendError",
    "ConversationRecord",
    "ConversationRepository",
    "ErrorCode",
    "ErrorEvent",
    "InMemoryConversationRepository",
    "InMemoryMessageStore",
    "MessageStore",
    "PostgresConversationRepository",
    "PostgresMessageStore",
    "StreamEvent",
    "ThinkingEvent",
    "ToolCallEvent",
    "ToolResultEvent",
]
