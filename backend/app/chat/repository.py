"""Conversation meta-CRUD repository (CONTEXT.md D-06).

Phase 6 / Plan 06-03 splits the legacy :class:`ConversationStore` ABC into
two narrower abstractions; this module owns the meta-CRUD half:

* :class:`ConversationRepository` — abstract base.
* :class:`InMemoryConversationRepository` — in-process impl for unit tests
  and the Phase 5 dev fallback path; uses an immutable-update pattern
  (``model_copy(update=...)``) for ``bump_last_activity`` so callers cannot
  observe a half-mutated record.
* :class:`PostgresConversationRepository` — production impl backed by the
  ``conversation`` SQLModel table from Plan 06-02.

Five concerns:

1. ``create`` — insert a new conversation row owned by ``user_id``.
2. ``get`` — single-row lookup by ``id``.
3. ``list_for_user`` — user-scoped index, sorted ``last_activity_at desc``.
4. ``bump_last_activity`` — narrow, dedicated update for SSE-stream activity
   markers (06-RESEARCH.md OQ-3 — preferred over a generic ``update`` for
   API-surface narrowness + test simplicity).
5. ``delete`` — drop the conversation; FK CASCADE removes child ``message``
   rows automatically.

The repository deliberately does NOT carry events; those live on
:class:`app.chat.store.MessageStore`. Splitting these along the events vs
meta-CRUD axis is what closes the Phase 5 verification CR-04 anti-pattern
(``ChatService._first_message_preview`` peeked into the in-memory store's
private ``_store`` dict via ``getattr``; the new
:meth:`MessageStore.first_user_message_preview` lives on the ABC and both
impls own it).

Per CLAUDE.md "all I/O must be ``async def``", every method on every
implementation is ``async def`` even though the in-memory impl never blocks.

The :class:`ConversationRecord` Pydantic DTO returned by ``get`` and
``list_for_user`` is a wire-internal shape distinct from
:class:`app.chat.models.ChatSessionInfo` (the route response model). Plan
06-04's :class:`ChatService` glue converts at the boundary.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from pydantic import BaseModel, Field
from sqlalchemy import update as sa_update
from sqlmodel import col, delete, select

from app.db.models import Conversation

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import async_sessionmaker
    from sqlmodel.ext.asyncio.session import AsyncSession


class ConversationRecord(BaseModel):
    """Wire-internal DTO returned by :class:`ConversationRepository` reads.

    Mirrors the canonical fields on :class:`app.db.models.Conversation`
    plus an optional ``first_message_preview`` so route handlers can build a
    :class:`app.chat.models.ChatSessionInfo` without a separate query path.
    The preview field stays ``None`` on :meth:`ConversationRepository.get`
    (single-row lookup) and is populated by :meth:`list_for_user` only when
    the impl has a cheap join to :class:`app.chat.store.MessageStore`'s
    first-message-preview source.

    Per CLAUDE.md Data Model Pattern: thin Pydantic model, no business
    logic beyond field declarations. The repository owns the storage
    semantics; the model owns only its shape.
    """

    id: UUID
    user_id: UUID
    provider: str
    model: str
    created_at: datetime
    last_activity_at: datetime
    first_message_preview: str | None = Field(
        default=None,
        description="First user-prompt content truncated to 80 chars; populated by list_for_user impls "
        "with a cheap MessageStore.first_user_message_preview join, otherwise None.",
    )


class ConversationRepository(ABC):
    """Abstract conversation meta-CRUD repository (D-06).

    Phase 6 contract: persist :class:`Conversation` rows scoped by
    ``user_id`` and expose the five CRUD concerns documented at module
    level. Both concrete impls (in-memory + Postgres) ship this wave;
    future :class:`RedisConversationRepository` or hybrid variants slot in
    via the same ABC without :class:`ChatService` changes.

    The user-scoped index (``user_id → conversation_id``) lives entirely on
    the impl — :class:`PostgresConversationRepository` uses the FK +
    ``user_id`` index from Plan 06-02; :class:`InMemoryConversationRepository`
    walks its dict and filters in Python.
    """

    @abstractmethod
    async def create(self, *, user_id: UUID, provider: str, model: str) -> UUID:
        """Insert a new conversation row owned by ``user_id``.

        Args:
            user_id: DB-native ``UUID`` primary key of the owning user.
            provider: Wire-level provider name (e.g. ``"ollama"``).
            model: Per-provider model identifier (e.g. ``"qwen3:4b"``).

        Returns:
            The freshly-generated conversation ``UUID``.
        """
        ...

    @abstractmethod
    async def get(self, conversation_id: UUID) -> ConversationRecord | None:
        """Return the conversation record by id, or ``None`` if missing.

        ``None`` is the documented contract for "missing or unknown" — the
        repository NEVER raises for missing keys (per the
        :class:`UserRepository` analog convention).

        Args:
            conversation_id: DB-native ``UUID`` primary key.

        Returns:
            The :class:`ConversationRecord`, or ``None`` if no row exists.
        """
        ...

    @abstractmethod
    async def list_for_user(self, user_id: UUID) -> list[ConversationRecord]:
        """Return all conversations owned by ``user_id`` sorted by activity.

        Sort order is ``last_activity_at DESC`` so the most-recently-active
        conversation appears first — matches the Phase 5 sidebar UX.

        Args:
            user_id: DB-native ``UUID`` primary key of the owning user.

        Returns:
            A list of :class:`ConversationRecord`; empty list when the user
            owns no conversations.
        """
        ...

    @abstractmethod
    async def bump_last_activity(self, conversation_id: UUID) -> None:
        """Update ``last_activity_at`` to ``now(UTC)`` for ``conversation_id``.

        Narrow dedicated method (06-RESEARCH.md OQ-3) — easier to test and
        easier to authorize at the route layer than a generic ``update``.

        No-op for unknown ``conversation_id``.

        Args:
            conversation_id: DB-native ``UUID`` primary key.
        """
        ...

    @abstractmethod
    async def delete(self, conversation_id: UUID) -> None:
        """Delete the conversation; FK CASCADE removes child message rows.

        No-op for unknown ``conversation_id``.

        Args:
            conversation_id: DB-native ``UUID`` primary key.
        """
        ...


class InMemoryConversationRepository(ConversationRepository):
    """In-process :class:`ConversationRepository` for unit tests + dev fallback.

    State lives in a single ``dict[UUID, ConversationRecord]``. The
    ``user_id → conversation_id`` index is computed on demand by
    :meth:`list_for_user` (a list comprehension over the dict's values) —
    cheap for the in-memory test scale, where the production index goes via
    SQL on the Postgres impl.

    :meth:`bump_last_activity` uses ``model_copy(update=...)`` so the stored
    record reference is replaced, not mutated. Callers holding the old
    reference observe a stable snapshot — same coding-style.md immutability
    rule that drives :meth:`InMemoryMessageStore.append`'s immutable concat.
    """

    def __init__(self) -> None:
        self._store: dict[UUID, ConversationRecord] = {}

    async def create(self, *, user_id: UUID, provider: str, model: str) -> UUID:
        """Generate a fresh ``UUID`` and persist a new :class:`ConversationRecord`."""
        now = datetime.now(UTC)
        conversation_id = uuid4()
        record = ConversationRecord(
            id=conversation_id,
            user_id=user_id,
            provider=provider,
            model=model,
            created_at=now,
            last_activity_at=now,
        )
        self._store[conversation_id] = record
        return conversation_id

    async def get(self, conversation_id: UUID) -> ConversationRecord | None:
        """Dict lookup; ``None`` when the conversation is unknown."""
        return self._store.get(conversation_id)

    async def list_for_user(self, user_id: UUID) -> list[ConversationRecord]:
        """Filter by ``user_id`` then sort by ``last_activity_at`` desc."""
        owned = [record for record in self._store.values() if record.user_id == user_id]
        owned.sort(key=lambda r: r.last_activity_at, reverse=True)
        return owned

    async def bump_last_activity(self, conversation_id: UUID) -> None:
        """Replace the stored record with an immutable model_copy(update=...).

        ``dict.get`` + early return makes this a no-op for unknown ids,
        matching the documented contract.
        """
        existing = self._store.get(conversation_id)
        if existing is None:
            return
        # Immutable update — never mutate ``existing`` in place.
        self._store[conversation_id] = existing.model_copy(update={"last_activity_at": datetime.now(UTC)})

    async def delete(self, conversation_id: UUID) -> None:
        """Drop the record; ``dict.pop(..., None)`` is a no-op for unknowns."""
        self._store.pop(conversation_id, None)


class PostgresConversationRepository(ConversationRepository):
    """Postgres-backed :class:`ConversationRepository` (D-06 prod impl).

    Talks directly to :class:`app.db.models.Conversation`. Each method
    opens its own short transaction via the injected
    ``async_sessionmaker`` — 06-RESEARCH.md Pitfall 3 forbids holding an
    :class:`AsyncSession` across an SSE handler, so per-method scoping
    keeps the pool churn predictable.

    The FK ``conversation.user_id → user.id ON DELETE CASCADE`` (Plan 06-02)
    plus the ``user_id`` index (Plan 06-02) is what makes
    :meth:`list_for_user` cheap and route-layer ownership checks viable.
    """

    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self._sessionmaker = sessionmaker

    async def create(self, *, user_id: UUID, provider: str, model: str) -> UUID:
        """Insert a new ``conversation`` row and return its generated ``id``."""
        async with self._sessionmaker() as session:
            row = Conversation(user_id=user_id, provider=provider, model=model)
            session.add(row)
            await session.commit()
            # ``Conversation.id`` is generated Python-side via ``default_factory=uuid4``
            # (Plan 06-02) so the value is available pre-commit; no refresh needed.
            return row.id

    async def get(self, conversation_id: UUID) -> ConversationRecord | None:
        """Single-row select by primary key; ``None`` when missing."""
        async with self._sessionmaker() as session:
            result = await session.execute(
                select(Conversation).where(col(Conversation.id) == conversation_id),
            )
            row = result.scalar_one_or_none()
        if row is None:
            return None
        return _to_record(row)

    async def list_for_user(self, user_id: UUID) -> list[ConversationRecord]:
        """User-scoped select sorted by ``last_activity_at desc``.

        FK + ``user_id`` index keeps the query cheap; SQL ORDER BY does the
        sort so the impl matches the in-memory contract verbatim.
        """
        async with self._sessionmaker() as session:
            result = await session.execute(
                select(Conversation)
                .where(col(Conversation.user_id) == user_id)
                .order_by(col(Conversation.last_activity_at).desc()),
            )
            rows = result.scalars().all()
        return [_to_record(row) for row in rows]

    async def bump_last_activity(self, conversation_id: UUID) -> None:
        """Issue a single-row UPDATE setting ``last_activity_at = now(UTC)``."""
        async with self._sessionmaker() as session:
            await session.execute(
                sa_update(Conversation)
                .where(col(Conversation.id) == conversation_id)
                .values(last_activity_at=datetime.now(UTC)),
            )
            await session.commit()

    async def delete(self, conversation_id: UUID) -> None:
        """Delete the conversation row; FK CASCADE removes child messages.

        The ``ON DELETE CASCADE`` on ``message.conversation_id`` (Plan
        06-02) is the V4-Access-Control mitigation: dropping a conversation
        cannot leave orphan message rows behind.
        """
        async with self._sessionmaker() as session:
            await session.execute(
                delete(Conversation).where(col(Conversation.id) == conversation_id),
            )
            await session.commit()


def _to_record(row: Conversation) -> ConversationRecord:
    """Map a :class:`Conversation` SQLModel row to a :class:`ConversationRecord`.

    Lives at module level so both ``get`` and ``list_for_user`` share the
    exact same field set — drift between the two would be a silent contract
    bug. ``first_message_preview`` is ``None`` here; impls that want to
    populate it MUST do so explicitly via a join to
    :meth:`MessageStore.first_user_message_preview` at the call site.
    """
    return ConversationRecord(
        id=row.id,
        user_id=row.user_id,
        provider=row.provider,
        model=row.model,
        created_at=row.created_at,
        last_activity_at=row.last_activity_at,
    )
