"""Phase 6 SQL schema — User / Conversation / Message tables (CONTEXT.md D-02).

This module is the **single source point** alembic targets via
``target_metadata = SQLModel.metadata``. Every SQLModel ``table=True`` class
defined here (or imported here) is registered on ``SQLModel.metadata`` at
import time, so :mod:`backend.migrations.env` only needs ``from app.db import
models  # noqa: F401`` to expose the full schema to ``alembic --autogenerate``
(06-RESEARCH.md Pitfall 2 — empty migrations when models aren't imported).

Schema (D-02 verbatim, Phase 6 CONTEXT.md):

* ``user`` — auth principal; replaces the Phase 5 env-backed user map (Plan 06-04).
* ``conversation`` — chat conversation metadata; ``user_id`` FK with
  ``ON DELETE CASCADE`` enforces ownership cleanup at the storage layer
  (V4 Access Control, threat T-06-02-01).
* ``message`` — append-only event log keyed by ``(conversation_id, seq)``;
  one ``ModelMessage`` per row, serialized via PydanticAI's
  ``ModelMessagesTypeAdapter`` into ``payload JSONB`` (D-02 rationale —
  matches LangGraph / OpenAI Agents SDK durable-state pattern, future
  agentic-state generation layers on top).

These classes are intentionally thin SQLModel tables (Data Model Pattern) —
no business logic, no validators in Phase 6. The store / repository
implementations in Plan 06-03 own the transactional behaviour
(append seq monotonicity, JSONB round-trip via ``to_jsonable_python`` +
``ModelMessagesTypeAdapter.validate_python``).

Composite unique index ``message_conv_seq`` on ``(conversation_id, seq)`` is
declared at module level after the class definitions — D-02 mandatory; the
unique constraint converts concurrent-append races into duplicate-key errors
the caller catches (06-RESEARCH.md Pitfall 6).
"""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Column, DateTime, ForeignKey, Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel


class User(SQLModel, table=True):
    """Auth principal row.

    Replaces the Phase 5 env-backed user map (Plan 06-04 deletes that
    path). ``hashed_password`` stores a pwdlib argon2 hash produced at seed
    time (Plan 06-06); plaintext is never persisted.
    """

    __tablename__ = "user"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    username: str = Field(unique=True, index=True, max_length=120)
    hashed_password: str = Field(max_length=200)
    disabled: bool = Field(default=False)
    # ``server_default="now()"`` lets Postgres assign timestamps on direct SQL
    # inserts (e.g., ``scripts/seed.py``'s ON CONFLICT upsert), independent of
    # the Python-side default in the SQLModel constructor.
    created_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default="now()"),
    )


class Conversation(SQLModel, table=True):
    """Chat conversation metadata row.

    The events for a conversation live in :class:`Message`; this row carries
    only the meta the API surfaces (provider, model, timestamps). FK
    ``user_id`` with ``ON DELETE CASCADE`` ensures deleting a user removes
    all their conversations (and, transitively via CASCADE on
    :class:`Message`, all their messages) — V4 Access Control mitigation
    for T-06-02-01.
    """

    __tablename__ = "conversation"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID = Field(
        sa_column=Column(
            ForeignKey("user.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
    )
    provider: str = Field(max_length=40)
    model: str = Field(max_length=120)
    created_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default="now()"),
    )
    last_activity_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default="now()"),
    )


class Message(SQLModel, table=True):
    """Append-only event log row (D-02).

    Each row stores one ``ModelMessage`` from PydanticAI, serialized via
    ``to_jsonable_python`` into the ``payload`` JSONB column. Replay uses
    ``SELECT payload FROM message WHERE conversation_id = $1 ORDER BY seq``
    + ``ModelMessagesTypeAdapter.validate_python`` (Plan 06-03 owns the
    impl).

    The ``id`` column is BIGSERIAL — alembic emits it as such because
    SQLAlchemy maps ``int`` PKs to integer-sequence types on Postgres; the
    ``id: int | None`` annotation lets the constructor leave it unset so the
    DB sequence assigns it.

    The composite unique index ``message_conv_seq`` on
    ``(conversation_id, seq)`` is declared on this table via
    ``__table_args__`` (D-02 mandatory). Two concurrent writers inserting at
    the same ``seq`` race the unique constraint — one succeeds, the other
    surfaces an ``IntegrityError`` the caller maps to a 409 / ``ErrorEvent``
    (06-RESEARCH.md Pitfall 6, threat T-06-02-03).
    """

    __tablename__ = "message"
    __table_args__ = (Index("message_conv_seq", "conversation_id", "seq", unique=True),)

    id: int | None = Field(default=None, primary_key=True)
    conversation_id: UUID = Field(
        sa_column=Column(
            ForeignKey("conversation.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
    )
    seq: int = Field(nullable=False)
    payload: dict = Field(sa_column=Column(JSONB, nullable=False))  # type: ignore[type-arg]
    created_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default="now()"),
    )
