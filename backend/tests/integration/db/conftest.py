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

from collections.abc import Generator

import pytest
from pytest_postgresql.executor_noop import NoopExecutor
from pytest_postgresql.factories import postgresql_noproc
from pytest_postgresql.janitor import DatabaseJanitor

# Pointed at the compose db (CONTEXT.md D-10). The helper-process model
# (``noproc``) reuses the live container instead of starting a second one.
postgresql_my_proc = postgresql_noproc(
    host="localhost",
    port=5432,
    user="trip_planner",
    password="trip_planner",
    dbname="trip_planner",
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
