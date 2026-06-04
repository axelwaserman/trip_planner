"""Async DB session factory for the Phase 6 DB stack.

Wires the application's :class:`Settings.database_url` into an
:class:`~sqlalchemy.ext.asyncio.AsyncEngine` and an
:class:`~sqlalchemy.ext.asyncio.async_sessionmaker` that produces
:class:`sqlmodel.ext.asyncio.session.AsyncSession` instances — SQLModel's
AsyncSession subclass keeps ``.exec()`` ergonomics aligned with the rest of
the codebase.

D-01 spike output: this is the artifact the spike proves works against a
live Postgres 16 container via ``postgresql+psycopg://``. Downstream Plan
06-03 stores (e.g. ``PostgresMessageStore``) accept ``_async_sessionmaker``
directly so they own their session lifecycles independently of FastAPI's
request-scoped dep — a streaming SSE handler must NOT hold an
``AsyncSession`` open across the whole stream (06-RESEARCH.md Pitfall 3).

``expire_on_commit=False`` is mandatory: with SQLAlchemy's default
(``True``) any attribute access after ``await session.commit()`` triggers
an implicit refresh, which becomes a sync I/O call in async-land and
raises ``MissingGreenlet`` (06-RESEARCH.md Pitfall 8).
"""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel.ext.asyncio.session import AsyncSession

from app.config import settings

# Module-level singleton engine. AsyncEngine is NOT fork-safe — when Phase 8
# introduces gunicorn workers each worker MUST construct its own engine
# ([CITED: docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html]). Single-process
# uvicorn (``just backend``) is the v1 deployment shape, so one engine here is fine.
engine = create_async_engine(
    settings.database_url,
    pool_size=settings.db_pool_size,
    max_overflow=settings.db_pool_overflow,
    echo=settings.debug,
)

# `class_=AsyncSession` selects SQLModel's AsyncSession subclass over SQLAlchemy's
# default — the subclass exposes a SQLModel-aware ``.exec()`` so callers don't have
# to switch idioms between sync and async paths.
_async_sessionmaker: async_sessionmaker[AsyncSession] = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_session() -> AsyncGenerator[AsyncSession]:
    """FastAPI dependency yielding a request-scoped async session.

    This is the **request-scoped** session dep — it opens a session at the
    start of a request and closes it at the end. Per-store implementations
    (e.g. ``PostgresMessageStore`` in Plan 06-03) receive ``_async_sessionmaker``
    directly via DI so they can manage their own session lifecycles, which
    matters for SSE handlers that must release the session before the stream
    body runs.

    Yields:
        AsyncSession: a SQLModel ``AsyncSession`` bound to the application's
        async engine, with ``expire_on_commit=False`` so model attributes
        stay accessible after ``await session.commit()``.
    """
    async with _async_sessionmaker() as session:
        yield session
