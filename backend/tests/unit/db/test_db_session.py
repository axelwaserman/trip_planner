"""Wave 0 spike smoke test for the Phase 6 DB stack (D-01 spike answer).

Three checks:

1. ``test_engine_url_uses_psycopg_async_dialect`` — pure inspection: assert the
   default ``Settings.database_url`` is wired through ``create_async_engine``
   under the ``postgresql+psycopg://`` URL scheme. No DB needed.

2. ``test_async_sessionmaker_disables_expire_on_commit`` — pure inspection:
   assert Pitfall 8 lock — ``expire_on_commit=False`` on the module-level
   ``async_sessionmaker``. No DB needed.

3. ``test_async_session_select_one_round_trip`` — live round-trip: open an
   ``AsyncSession``, run ``SELECT 1``, assert ``scalar_one() == 1``. Skips
   cleanly when Postgres is not reachable on ``localhost:5432``; this is the
   D-01 spike's actual proof that the stack works.

Path-based test selection per CLAUDE.md — file lives under ``tests/unit/db/``
so ``pytest tests/unit/db`` picks it up; no ``pytest.mark.unit`` decorator.
``asyncio_mode = "auto"`` (in ``pyproject.toml``) makes ``async def`` tests
run without explicit ``@pytest.mark.asyncio`` decorators.
"""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from app.db.session import _async_sessionmaker, engine

_POSTGRES_SKIP_REASON = (
    "Postgres unavailable on localhost:5432 — start with "
    "`docker run --rm -p 5432:5432 -e POSTGRES_PASSWORD=trip_planner "
    "-e POSTGRES_USER=trip_planner -e POSTGRES_DB=trip_planner postgres:16-alpine`"
)


def test_engine_url_uses_psycopg_async_dialect() -> None:
    """The async engine must speak ``postgresql+psycopg://`` (D-01 spike contract).

    SQLAlchemy 2.0 + psycopg 3 async support is the locked driver per
    ADR-006; any other dialect would mean a fallback path landed silently.
    """
    assert str(engine.url).startswith("postgresql+psycopg://"), str(engine.url)


def test_async_sessionmaker_disables_expire_on_commit() -> None:
    """Pitfall 8 lock: ``expire_on_commit`` MUST be False.

    The default (``True``) refreshes loaded attributes after commit; in
    async-land that refresh is a sync I/O call that explodes with
    ``MissingGreenlet``. Documented in 06-RESEARCH.md §Pitfall 8.
    """
    assert _async_sessionmaker.kw["expire_on_commit"] is False


# SQLModel's AsyncSession emits a DeprecationWarning urging callers to use
# ``.exec()`` instead of ``.execute()`` — but ``.exec()`` is statically typed
# only against ``Select`` / ``SelectOfScalar`` / ``UpdateBase`` and rejects
# raw ``text()`` clauses under ``mypy --strict``. For a raw ``SELECT 1`` smoke
# we keep ``.execute(text(...))`` and silence the SQLModel-only suggestion via
# ``@pytest.mark.filterwarnings`` (the canonical pytest path — local
# ``warnings.catch_warnings()`` is overridden by pytest's per-test recorder).
# The canonical ORM path will switch to ``.exec()`` with proper Select
# statements once Plan 06-02 lands the SQLModel tables.
@pytest.mark.filterwarnings("ignore::DeprecationWarning:tests.unit.db.test_db_session")
async def test_async_session_select_one_round_trip() -> None:
    """Open a session, run ``SELECT 1``, assert the round-trip works.

    This is the D-01 spike's proof against a live Postgres 16 container.
    Skips cleanly when Postgres is not reachable on ``localhost:5432`` so
    CI without a compose ``db`` service does not fail; running with the
    spike credentials makes the test pass.
    """
    try:
        async with _async_sessionmaker() as session:
            result = await session.execute(text("SELECT 1"))
            assert result.scalar_one() == 1
    except OperationalError:
        pytest.skip(_POSTGRES_SKIP_REASON)
