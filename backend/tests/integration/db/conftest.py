"""Integration-test DB fixtures — pytest-postgresql against the compose db.

Phase 6 integration tests (D-02 schema, alembic round-trip, future Plan 06-03
store tests) need a clean Postgres per test without paying ~2-3s container
startup. ``pytest-postgresql``'s ``postgresql_noproc`` factory wraps the
template-clone mechanism: it connects to the **already-running** Postgres
(the compose ``db`` service or a host-side ``docker run`` instance — Plan
01 Task 3 / Plan 06-06), creates a per-test database from a template, and
drops it on teardown. Setup is O(ms).

This conftest does NOT auto-run anything; integration tests opt in by
requesting the ``pg_database_url`` fixture. Tests in unrelated directories
are unaffected.

Precondition: Postgres on ``localhost:5432`` with the trip_planner / trip_planner
credentials (matches CONTEXT.md D-10 compose shape). When unavailable, tests
that request ``pg_database_url`` error loudly during fixture setup — they do
NOT silently skip. Bring up the compose stack (``just compose-up`` once Plan
06-06 lands) or the manual ``docker run`` from 06-01-SUMMARY.md.
"""

import os
from collections.abc import Generator
from urllib.parse import urlparse

import pytest
from pytest_postgresql.executor_noop import NoopExecutor
from pytest_postgresql.factories import postgresql_noproc
from pytest_postgresql.janitor import DatabaseJanitor


def _resolve_pg_target() -> tuple[str, int, str, str, str]:
    """Resolve Postgres target from env, falling back to compose defaults.

    Compose default is ``localhost:5432`` (CONTEXT.md D-10), but ``POSTGRES_HOST_PORT``
    in ``.env`` (Pitfall 4) may override the host port — and developers may run
    the phase-6 db service alongside another local Postgres on 5432. Reading
    ``DATABASE_URL`` keeps tests honest against whatever the running app uses.
    """
    raw = os.environ.get("DATABASE_URL")
    if raw:
        # SQLAlchemy URL form ``postgresql+psycopg://...`` parses with urlparse
        # once the ``+psycopg`` driver suffix is stripped.
        parsed = urlparse(raw.replace("postgresql+psycopg://", "postgresql://"))
        host = parsed.hostname or "localhost"
        port = parsed.port or 5432
        user = parsed.username or "trip_planner"
        password = parsed.password or "trip_planner"
        dbname = (parsed.path or "/trip_planner").lstrip("/") or "trip_planner"
        return host, port, user, password, dbname
    return (
        "localhost",
        int(os.environ.get("POSTGRES_HOST_PORT", "5432")),
        "trip_planner",
        "trip_planner",
        "trip_planner",
    )


_PG_HOST, _PG_PORT, _PG_USER, _PG_PASSWORD, _PG_DBNAME = _resolve_pg_target()

# Pointed at the compose db (CONTEXT.md D-10). The helper-process model
# (``noproc``) reuses the live container instead of starting a second one.
postgresql_my_proc = postgresql_noproc(
    host=_PG_HOST,
    port=_PG_PORT,
    user=_PG_USER,
    password=_PG_PASSWORD,
    dbname=_PG_DBNAME,
)


@pytest.fixture
def pg_database_url(postgresql_my_proc: NoopExecutor) -> Generator[str]:
    """Yield a per-test ``postgresql+psycopg://`` URL targeting a clean DB.

    Uses ``DatabaseJanitor`` directly (rather than chaining on the
    ``postgresql`` connection fixture) so we get a fresh database whose
    connection identity isn't bound to a still-open libpq connection. The
    janitor creates the database before yield and drops it after, isolating
    every test's schema state.

    Yields:
        A ``postgresql+psycopg://user:pass@host:port/dbname`` URL pointing at
        the per-test database. Suitable for ``create_async_engine`` or for
        injection into a subprocess via ``DATABASE_URL``.
    """
    # Per-test database name — keeps tests parallel-safe and prevents schema
    # state from one test leaking into the next.
    dbname = f"test_phase06_{id(postgresql_my_proc)}"
    user = postgresql_my_proc.user
    password = postgresql_my_proc.password
    host = postgresql_my_proc.host
    port = postgresql_my_proc.port

    with DatabaseJanitor(
        user=user,
        password=password,
        host=host,
        port=port,
        dbname=dbname,
        version=postgresql_my_proc.version,
    ):
        yield f"postgresql+psycopg://{user}:{password}@{host}:{port}/{dbname}"
