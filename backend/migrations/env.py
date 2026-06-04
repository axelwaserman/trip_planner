"""Alembic async env.py — wires SQLModel.metadata + Settings.database_url.

The async migration runner wraps :func:`do_run_migrations` in
``connection.run_sync(...)`` inside an :class:`AsyncEngine` connect block per
the alembic cookbook ([CITED: alembic.sqlalchemy.org/en/latest/cookbook.html
#using-asyncio-with-alembic]).

CRITICAL ordering (06-RESEARCH.md Pitfall 2): import every module that
defines SQLModel ``table=True`` classes BEFORE assigning
``target_metadata = SQLModel.metadata``. If the import is missing or comes
after the assignment, ``alembic --autogenerate`` produces an empty migration
because no tables are registered on ``SQLModel.metadata`` at the time
``EnvironmentContext.configure`` reads it.
"""

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config
from sqlmodel import SQLModel

# CRITICAL — register every table on SQLModel.metadata BEFORE the
# ``target_metadata = SQLModel.metadata`` assignment below. The ``noqa: F401``
# silences ruff's unused-import warning; the import side-effect IS the point.
# These app.* imports follow the alembic + sqlmodel imports because env.py is
# only ever invoked via ``uv run alembic …`` from ``backend/`` so app.* is on
# sys.path; isort treats them as first-party (per pyproject `known-first-party`).
from app.config import settings
from app.db import models  # noqa: F401  (registers User/Conversation/Message)

# Alembic config object (proxy for the parsed alembic.ini).
config = context.config

# Inject the application's database URL so alembic and the app agree on the
# target. ``alembic.ini`` ships with a blank ``sqlalchemy.url``; this line is
# the canonical (and ONLY) place that URL is set at runtime.
config.set_main_option("sqlalchemy.url", settings.database_url)

# Interpret the config file for Python logging (alembic-managed loggers).
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Target metadata — alembic --autogenerate compares this against the live DB
# to emit op.* DDL operations. SQLModel.metadata aggregates every ``table=True``
# class imported above.
target_metadata = SQLModel.metadata


def do_run_migrations(connection: Connection) -> None:
    """Configure and execute migrations on a sync-style connection.

    Called inside ``connection.run_sync(...)`` from the async runner.
    ``compare_type=True`` tells alembic to detect column-type drift (e.g.,
    VARCHAR(120) → VARCHAR(200)). ``render_as_batch=False`` because Postgres
    supports DDL transactions natively (batch mode is for SQLite).
    """
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        render_as_batch=False,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Build an :class:`AsyncEngine`, connect, and dispatch sync migration logic.

    ``poolclass=pool.NullPool`` because alembic runs as a one-shot CLI — no
    long-lived pool needed; opening one connection and disposing the engine
    is the minimal-state pattern.
    """
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Online-mode entrypoint — schedules the async runner."""
    asyncio.run(run_async_migrations())


def run_migrations_offline() -> None:
    """Offline (SQL-emit) mode — emits DDL strings without a DB connection.

    Reuses ``target_metadata`` so ``alembic upgrade --sql`` outputs a valid
    SQL script even when no DB is reachable.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
