"""Persistent chat message storage (D-05).

Phase 6 / Plan 06-03 split the Phase 5 :class:`ConversationStore` ABC into
two narrower abstractions per CONTEXT.md D-05/D-06; Phase 6 / Plan 06-04
deleted the legacy :class:`ConversationStore` shim once :class:`ChatService`
was rewired onto the split:

* :class:`MessageStore` (this module) — append-only event log: the
  ``list[ModelMessage]`` round-trip used by :meth:`ChatService.chat_stream`,
  plus :meth:`MessageStore.first_user_message_preview` — the canonical CR-04
  fix from Phase 5 verification.
* :class:`app.chat.repository.ConversationRepository` (sibling module) —
  meta-CRUD: ``create`` / ``get`` / ``list_for_user`` / ``bump_last_activity``
  / ``delete``. Conversation metadata (provider/model/timestamps) lives in
  SQL on the ``conversation`` row, not on a Python ``_metadata`` dict.

Per D-09, the in-memory impl stores only what the in-memory tests need; the
authoritative user-scoped index lives on
:class:`app.chat.repository.PostgresConversationRepository`.

Per CLAUDE.md "all I/O must be ``async def``", every method on every store
is ``async def`` even though the in-memory impl never blocks — the ABC must
match what the Postgres impl requires.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from pydantic_ai.messages import (
    ModelMessage,
    ModelMessagesTypeAdapter,
    ModelRequest,
    UserPromptPart,
)
from pydantic_core import to_jsonable_python
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlmodel import col, delete, select

from app.config import settings
from app.db.models import Message

if TYPE_CHECKING:
    from uuid import UUID

    from sqlalchemy.ext.asyncio import async_sessionmaker
    from sqlmodel.ext.asyncio.session import AsyncSession


# Truncation length for first_user_message_preview — kept module-level (not on
# Settings) because the value is part of the wire contract: ``ChatSessionInfo
# .first_message_preview`` is documented as "truncated to 80 chars" and the
# frontend truncates accordingly. Per CLAUDE.md, contract values stay as
# module constants; tunables (e.g. ``message_max_payload_bytes``) live on
# Settings.
_PREVIEW_MAX_LENGTH = 80


class ConversationConcurrentAppendError(RuntimeError):
    """Raised when two writers race the ``(conversation_id, seq)`` unique index.

    Phase 6 / 06-RESEARCH.md Pitfall 6 + threat T-06-03-04: the
    ``SELECT max(seq) … then INSERT`` pattern is not atomic across concurrent
    writers, so the unique index is the safety net. This exception surfaces
    the resulting ``IntegrityError`` as a domain-level signal so
    :class:`ChatService` (Plan 06-04) can map it to a clear
    :class:`app.chat.models.ErrorEvent` rather than letting the SQL error
    propagate to the SSE wire (V4 Access Control + repudiation lock).

    The single-writer-per-conversation invariant (06-RESEARCH.md Assumption
    A4) means this should be rare in v1; it exists primarily as a
    defence-in-depth lock for the Phase 5 verification finding WR-01
    (concurrent ``chat_stream`` calls on the same conversation).
    """

    def __init__(self, conversation_id: UUID) -> None:
        super().__init__(
            f"Concurrent append detected on conversation {conversation_id}; "
            "another writer raced the (conversation_id, seq) unique index.",
        )
        self.conversation_id = conversation_id


class MessageStore(ABC):
    """Abstract message-event store keyed by ``conversation_id`` (D-05).

    Phase 6 contract: persist a per-conversation ``list[ModelMessage]`` and
    expose minimal append-only operations against it. Both concrete impls
    (in-memory + Postgres) ship this wave; future :class:`RedisMessageStore`
    or hybrid Redis-hot/PG-durable variants slot in via the same ABC without
    :class:`ChatService` changes.

    :meth:`first_user_message_preview` lives on the ABC so that
    :meth:`ChatService.list_sessions_for_user` no longer reaches into a
    private ``_store`` dict via ``getattr`` (CR-04 from Phase 5 verification).
    The PG impl owns it as a SQL query; the in-memory impl owns it as a list
    walk — both satisfy the same observable shape.
    """

    @abstractmethod
    async def append(self, conversation_id: UUID, messages: list[ModelMessage]) -> None:
        """Append ``messages`` to the conversation's history.

        Implementations MUST treat the existing history as immutable and
        produce a new list internally (per
        ``~/.claude/rules/common/coding-style.md`` immutability rule). Append
        is the only mutation; in-place edits are not supported.

        Args:
            conversation_id: DB-native ``UUID`` primary key of the
                ``conversation`` row.
            messages: One or more :class:`ModelMessage` instances to append.
                The list is opaque to the store — element shape is owned by
                PydanticAI.

        Raises:
            ConversationConcurrentAppendError: When a Postgres impl detects
                a unique-index collision on ``(conversation_id, seq)`` —
                another writer raced this one. The in-memory impl never
                raises this.
            ValueError: When a serialized payload exceeds
                :attr:`Settings.message_max_payload_bytes` (Pitfall 5
                guardrail). The Postgres impl enforces this; the in-memory
                impl does not.
        """
        ...

    @abstractmethod
    async def load(self, conversation_id: UUID) -> list[ModelMessage]:
        """Load the conversation's full message history in append order.

        Args:
            conversation_id: DB-native ``UUID`` primary key.

        Returns:
            A list of :class:`ModelMessage` ordered by append sequence; empty
            list when the conversation is unknown (the store NEVER raises
            for missing keys — per the :class:`UserRepository` analog).
        """
        ...

    @abstractmethod
    async def delete(self, conversation_id: UUID) -> None:
        """Remove the conversation's message history. No-op for unknowns.

        Args:
            conversation_id: DB-native ``UUID`` primary key.
        """
        ...

    @abstractmethod
    async def first_user_message_preview(self, conversation_id: UUID) -> str | None:
        """Return the conversation's first user-prompt content (truncated).

        Walks the conversation's message history and returns
        ``content[:80]`` of the first :class:`UserPromptPart` found on a
        :class:`ModelRequest`. ``None`` when the conversation is unknown or
        carries no user-prompt yet.

        This method exists on the ABC (D-05) so
        :meth:`ChatService.list_sessions_for_user` no longer peeks into a
        private ``_store`` dict via ``getattr`` (CR-04 anti-pattern lock).

        Args:
            conversation_id: DB-native ``UUID`` primary key.

        Returns:
            The first user-prompt text truncated to 80 characters, or
            ``None`` if no user-prompt exists yet.
        """
        ...


class InMemoryMessageStore(MessageStore):
    """In-memory :class:`MessageStore` for unit tests + dev fallback.

    State lives in a single private dict ``_store: dict[UUID,
    list[ModelMessage]]``. Round-trip via ``append`` then ``load`` returns a
    defensive copy of the stored list so callers cannot mutate the store's
    internal state — same invariant as
    :class:`app.auth.repository.EnvUserRepository.get_user`'s ``UserInDB``
    returns.

    Unlike the legacy :class:`InMemoryConversationStore`, this impl does NOT
    track a ``user_id → conversation_id`` index; that responsibility now
    lives on :class:`app.chat.repository.InMemoryConversationRepository`
    (D-06 split).
    """

    def __init__(self) -> None:
        self._store: dict[UUID, list[ModelMessage]] = {}

    async def append(self, conversation_id: UUID, messages: list[ModelMessage]) -> None:
        """Append ``messages`` immutably (``existing + messages``)."""
        existing = self._store.get(conversation_id, [])
        # Immutable concat per coding-style.md — never `.append()` in place.
        self._store[conversation_id] = existing + messages

    async def load(self, conversation_id: UUID) -> list[ModelMessage]:
        """Return a defensive copy of the conversation's history (empty list when unknown)."""
        return list(self._store.get(conversation_id, []))

    async def delete(self, conversation_id: UUID) -> None:
        """Drop the conversation entry. ``dict.pop(..., None)`` makes this a no-op for unknowns."""
        self._store.pop(conversation_id, None)

    async def first_user_message_preview(self, conversation_id: UUID) -> str | None:
        """Return the first user-prompt content truncated to 80 chars, or None."""
        messages = self._store.get(conversation_id, [])
        return _extract_first_user_prompt_preview(messages)


class PostgresMessageStore(MessageStore):
    """Postgres-backed :class:`MessageStore` (06-RESEARCH.md Pattern 3).

    Each :class:`ModelMessage` round-trips through the ``message`` table's
    ``payload`` JSONB column via
    :func:`pydantic_core.to_jsonable_python` on append and
    :class:`pydantic_ai.messages.ModelMessagesTypeAdapter` on load. The
    ``(conversation_id, seq)`` composite unique index defined in
    :mod:`app.db.models` (Plan 06-02) is the safety net for concurrent
    writers (Pitfall 6) — :meth:`append` maps the resulting
    :class:`sqlalchemy.exc.IntegrityError` to
    :class:`ConversationConcurrentAppendError` so the ChatService layer can
    surface a domain error instead of letting raw SQL bubble up.

    The store is constructed with an ``async_sessionmaker`` (not a single
    long-lived session) so each call manages its own short transaction —
    06-RESEARCH.md Pitfall 3 forbids holding an :class:`AsyncSession` across
    a streaming SSE handler.
    """

    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self._sessionmaker = sessionmaker

    async def append(self, conversation_id: UUID, messages: list[ModelMessage]) -> None:
        """Append ``messages`` as event-log rows; reject oversize payloads.

        Steps (RESEARCH Pattern 3):

        1. Serialize each :class:`ModelMessage` via
           :func:`to_jsonable_python` and compute its UTF-8 byte length.
           Anything exceeding :attr:`Settings.message_max_payload_bytes` is
           rejected with :class:`ValueError` BEFORE issuing any INSERT
           (Pitfall 5 / threat T-06-03-05). The whole batch fails if any
           single payload is too large — partial writes would corrupt the
           ordered log.
        2. ``SELECT coalesce(max(seq), 0)`` for the conversation, then build
           one :class:`Message` per input with monotonic
           ``seq = current_max + offset``.
        3. ``await session.commit()``; on
           :class:`sqlalchemy.exc.IntegrityError` (the
           ``(conversation_id, seq)`` unique-index race) re-raise as
           :class:`ConversationConcurrentAppendError`.
        """
        # Pitfall 5 / T-06-03-05: cap row size before any DB work so an
        # oversize payload doesn't waste a round-trip + a session checkout.
        # Serialize once, reuse for the INSERT — keeps the CPU cost flat.
        serialized: list[tuple[ModelMessage, dict[str, object]]] = []
        for msg in messages:
            payload = to_jsonable_python(msg)
            # ``to_jsonable_python`` returns a Python object tree. Serialize to
            # JSON bytes for the size check so the cap matches what JSONB will
            # actually store on disk. ``ensure_ascii=False`` keeps non-ASCII
            # text at its true byte size (the JSONB column is UTF-8 by default).
            import json as _stdjson  # noqa: PLC0415 — avoid leaking the alias to module surface

            payload_bytes = len(_stdjson.dumps(payload, ensure_ascii=False).encode("utf-8"))
            if payload_bytes > settings.message_max_payload_bytes:
                raise ValueError(
                    f"ModelMessage payload size {payload_bytes} bytes exceeds "
                    f"message_max_payload_bytes={settings.message_max_payload_bytes}",
                )
            serialized.append((msg, payload))

        # ``sqlmodel.select`` + ``sqlmodel.col`` is the mypy-strict-friendly
        # combo: SQLModel's class-level descriptors are typed as the Python
        # field type (UUID/int/dict) for end-user ergonomics, so a bare
        # ``Message.conversation_id == cid`` resolves to ``bool`` under
        # ``--strict``. ``col(Message.x)`` re-types the descriptor as a
        # ``ColumnClause`` so where/order_by accept it cleanly.
        async with self._sessionmaker() as session:
            current_max_result = await session.execute(
                select(func.coalesce(func.max(col(Message.seq)), 0)).where(
                    col(Message.conversation_id) == conversation_id,
                ),
            )
            current_max = current_max_result.scalar_one()
            for offset, (_msg, payload) in enumerate(serialized, start=1):
                session.add(
                    Message(
                        conversation_id=conversation_id,
                        seq=current_max + offset,
                        payload=payload,
                    ),
                )
            try:
                await session.commit()
            except IntegrityError as exc:
                # Pitfall 6 / T-06-03-04: surface the unique-violation as a
                # domain-level signal so the caller can map it to a clear
                # ErrorEvent rather than 500'ing on raw SQL state.
                raise ConversationConcurrentAppendError(conversation_id) from exc

    async def load(self, conversation_id: UUID) -> list[ModelMessage]:
        """Replay the conversation's event log via JSONB → ``ModelMessage``."""
        async with self._sessionmaker() as session:
            result = await session.execute(
                select(Message.payload)
                .where(col(Message.conversation_id) == conversation_id)
                .order_by(col(Message.seq)),
            )
            rows = list(result.scalars().all())
        if not rows:
            return []
        # ModelMessagesTypeAdapter.validate_python reconstitutes the full
        # list[ModelMessage] from the JSONB-shape Python objects.
        return ModelMessagesTypeAdapter.validate_python(rows)

    async def delete(self, conversation_id: UUID) -> None:
        """Truncate the conversation's event log.

        Note: deleting the parent ``conversation`` row triggers ON DELETE
        CASCADE, which removes child ``message`` rows automatically. This
        method exists for explicit per-conversation truncation (e.g. tests,
        future "clear history" UX) without dropping the conversation row.
        """
        async with self._sessionmaker() as session:
            await session.execute(
                delete(Message).where(col(Message.conversation_id) == conversation_id),
            )
            await session.commit()

    async def first_user_message_preview(self, conversation_id: UUID) -> str | None:
        """Return the first ``UserPromptPart`` content truncated to 80 chars.

        Loads the earliest message row by ``seq`` and decodes its JSONB
        payload back into a :class:`ModelMessage`. Returning ``None`` here
        is the documented contract for "no user-prompt yet" — empty
        conversation, or a leading non-request message (rare).
        """
        async with self._sessionmaker() as session:
            result = await session.execute(
                select(Message.payload)
                .where(col(Message.conversation_id) == conversation_id)
                .order_by(col(Message.seq))
                .limit(1),
            )
            row = result.scalar_one_or_none()
        if row is None:
            return None
        # Reuse the canonical adapter so JSONB → ModelMessage stays in one place.
        messages = ModelMessagesTypeAdapter.validate_python([row])
        return _extract_first_user_prompt_preview(messages)


def _extract_first_user_prompt_preview(messages: list[ModelMessage]) -> str | None:
    """Walk ``messages`` and return the first ``UserPromptPart`` content (≤80 chars).

    Shared between :class:`InMemoryMessageStore` and
    :class:`PostgresMessageStore` so the truncation rule lives in exactly one
    place. ``content`` is canonically a ``str`` on PydanticAI's
    :class:`UserPromptPart`; the ``str(content)`` fallback exists only to
    cover the documented multimodal case (image/file content) which
    Phase 6 has no LLM in scope for.
    """
    for msg in messages:
        if isinstance(msg, ModelRequest):
            for part in msg.parts:
                if isinstance(part, UserPromptPart):
                    content = part.content
                    if isinstance(content, str):
                        return content[:_PREVIEW_MAX_LENGTH]
                    return str(content)[:_PREVIEW_MAX_LENGTH]
    return None


