"""Engine and session factory."""

from __future__ import annotations

from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings


@lru_cache
def get_engine() -> Engine:
    return create_engine(
        get_settings().database_url,
        pool_pre_ping=True,
        pool_size=5,
        # Supabase's pooler (Supavisor, transaction mode) hands each logical
        # connection off across different backend server connections, so a
        # server-side prepared statement from one can collide with another —
        # psycopg3's own auto-preparation (default: after 5 uses of a similar
        # statement) then fails with "prepared statement already exists".
        # Disabling it is the standard fix for psycopg3 behind a transaction
        # pooler; harmless against a direct (non-pooled) connection too.
        connect_args={"prepare_threshold": None},
    )


@lru_cache
def get_sessionmaker() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), expire_on_commit=False)


def get_db() -> Iterator[Session]:
    """FastAPI dependency: one session per request."""
    session = get_sessionmaker()()
    try:
        yield session
    finally:
        session.close()
