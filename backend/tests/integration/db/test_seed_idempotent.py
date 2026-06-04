"""Integration tests: ``scripts/seed.py`` against the per-test DB.

Plan 06-06 Task 2 — locks idempotent seed behaviour:

* Re-running the seed leaves the row count unchanged but refreshes the
  argon2 hash (random salt → different ciphertext per call).
* The ``disabled`` flag updates in place via ``ON CONFLICT DO UPDATE``.
* Non-local ``database_url`` aborts with returncode 2 when
  ``seed_allow_non_local`` is False.
* Missing TOML returns 1; empty users-list returns 0.

Path-based selection (CLAUDE.md): the file lives under
``tests/integration/db/`` so ``just test-integration`` picks it up; no
``@pytest.mark.integration`` marker.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.auth.repository import _password_hasher
from app.config import settings
from scripts.seed import seed

if TYPE_CHECKING:
    import pytest

# `backend/` — the directory that contains alembic.ini.
_BACKEND_DIR = Path(__file__).resolve().parents[3]


def _run_alembic_upgrade(database_url: str) -> None:
    """Apply alembic head against the per-test database."""
    env = {**os.environ, "DATABASE_URL": database_url}
    subprocess.run(  # noqa: S603 — trusted args, no shell
        ["uv", "run", "alembic", "upgrade", "head"],
        cwd=_BACKEND_DIR,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )


def _write_seed(tmp_path: Path, users: list[dict[str, object]]) -> Path:
    """Write a TOML file with the given ``[[users]]`` entries; return the path."""
    toml_path = tmp_path / "seed.toml"
    blocks: list[str] = []
    for entry in users:
        block = (
            "[[users]]\n"
            f'username = "{entry["username"]}"\n'
            f'password = "{entry["password"]}"\n'
            f"disabled = {str(entry['disabled']).lower()}\n"
        )
        blocks.append(block)
    toml_path.write_text("\n".join(blocks))
    return toml_path


async def _fetch_user_row(database_url: str, username: str) -> tuple[int, str | None, bool | None]:
    """Return (count, hashed_password, disabled) for *username*."""
    engine = create_async_engine(database_url)
    try:
        async with engine.connect() as conn:
            count_row = await conn.execute(
                text('SELECT count(*) FROM "user" WHERE username = :u'),
                {"u": username},
            )
            count = int(count_row.scalar_one())
            row = await conn.execute(
                text('SELECT hashed_password, disabled FROM "user" WHERE username = :u'),
                {"u": username},
            )
            data = row.first()
    finally:
        await engine.dispose()
    if data is None:
        return count, None, None
    return count, str(data[0]), bool(data[1])


async def test_seed_inserts_and_is_idempotent_on_re_run(
    pg_database_url: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """First run inserts; second run keeps the row count and refreshes the hash."""
    _run_alembic_upgrade(pg_database_url)
    monkeypatch.setattr(settings, "database_url", pg_database_url)

    toml_path = _write_seed(
        tmp_path,
        [{"username": "seedtest", "password": "pw", "disabled": False}],
    )

    # First run — fresh insert.
    rc1 = await seed(toml_path)
    assert rc1 == 0
    count1, hash1, _ = await _fetch_user_row(pg_database_url, "seedtest")
    assert count1 == 1
    assert hash1 is not None
    assert _password_hasher.verify("pw", hash1) is True

    # Second run — same TOML; row count unchanged but hash re-rolls
    # (argon2 random salt makes every hash() call produce a distinct string,
    # so a stable hash would prove ON CONFLICT DO UPDATE was a no-op rather
    # than refreshing the row).
    rc2 = await seed(toml_path)
    assert rc2 == 0
    count2, hash2, _ = await _fetch_user_row(pg_database_url, "seedtest")
    assert count2 == 1
    assert hash2 is not None
    assert hash2 != hash1
    assert _password_hasher.verify("pw", hash2) is True


async def test_seed_updates_disabled_flag_in_place(
    pg_database_url: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ON CONFLICT DO UPDATE refreshes the ``disabled`` column."""
    _run_alembic_upgrade(pg_database_url)
    monkeypatch.setattr(settings, "database_url", pg_database_url)

    toml_off = _write_seed(
        tmp_path,
        [{"username": "togglable", "password": "pw", "disabled": False}],
    )
    assert await seed(toml_off) == 0
    count, _, disabled = await _fetch_user_row(pg_database_url, "togglable")
    assert count == 1
    assert disabled is False

    toml_on = _write_seed(
        tmp_path,
        [{"username": "togglable", "password": "pw", "disabled": True}],
    )
    assert await seed(toml_on) == 0
    count, _, disabled = await _fetch_user_row(pg_database_url, "togglable")
    assert count == 1
    assert disabled is True


async def test_seed_aborts_against_non_local_database_url_without_override(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Non-local URL with ``seed_allow_non_local=False`` returns 2; no DB call."""
    monkeypatch.setattr(
        settings,
        "database_url",
        "postgresql+psycopg://x:y@example.com:5432/z",
    )
    monkeypatch.setattr(settings, "seed_allow_non_local", False)

    toml_path = _write_seed(
        tmp_path,
        [{"username": "should-not-insert", "password": "pw", "disabled": False}],
    )

    rc = await seed(toml_path)
    assert rc == 2
    captured = capsys.readouterr()
    assert "non-local" in captured.err


async def test_seed_returns_1_when_toml_missing(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Missing TOML → returncode 1 + stderr message."""
    rc = await seed(tmp_path / "does-not-exist.toml")
    assert rc == 1
    captured = capsys.readouterr()
    assert "not found" in captured.err


async def test_seed_handles_empty_users_table(
    pg_database_url: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """TOML with no ``[[users]]`` blocks → returncode 0, no rows changed."""
    _run_alembic_upgrade(pg_database_url)
    monkeypatch.setattr(settings, "database_url", pg_database_url)

    toml_path = tmp_path / "empty.toml"
    toml_path.write_text('[meta]\nphase = "6"\n')

    rc = await seed(toml_path)
    assert rc == 0

    engine = create_async_engine(pg_database_url)
    try:
        async with engine.connect() as conn:
            count_row = await conn.execute(text('SELECT count(*) FROM "user"'))
            assert int(count_row.scalar_one()) == 0
    finally:
        await engine.dispose()
