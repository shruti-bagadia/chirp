"""Shared test helpers.

`get_test_db_url()` points every `tests/api` DB fixture at a dedicated `..._test`
database instead of the one `DATABASE_URL` names for real dev use — those fixtures
`drop_all`/`create_all` on every run, and doing that against the same database
`make dev` reads from means every `pytest` wipes your local dashboard data.
"""

from __future__ import annotations

import time

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine.url import make_url
from sqlalchemy.exc import OperationalError

from app.core.config import get_settings


def with_retries(fn, attempts: int = 5, delay: float = 0.4):
    """This machine's local Docker/loopback networking occasionally corrupts a
    connection mid-handshake, which surfaces as Postgres SCRAM auth failing even
    though the password is right. Retrying a fresh connection attempt (everything
    called through this is idempotent: connect, CREATE EXTENSION, drop/create
    tables) works around it instead of failing the whole test run.
    """
    last: OperationalError | None = None
    for attempt in range(attempts):
        try:
            return fn()
        except OperationalError as exc:
            last = exc
            time.sleep(delay * (attempt + 1))
    raise last


def get_test_db_url() -> str:
    url = make_url(get_settings().database_url)
    test_db = f"{url.database or 'chirp'}_test"
    test_url = url.set(database=test_db)

    def _ensure() -> None:
        admin_engine = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
        try:
            with admin_engine.connect() as c:
                exists = c.execute(
                    text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": test_db}
                ).first()
                if not exists:
                    c.execute(text(f'CREATE DATABASE "{test_db}"'))
        finally:
            admin_engine.dispose()

    try:
        with_retries(_ensure)
    except OperationalError:
        pytest.skip("No Postgres available")
    # `str(url)` masks the password as `***` (safe-for-logging default) — render it
    # for real, or every connection using this string authenticates as password '***'.
    return test_url.render_as_string(hide_password=False)
