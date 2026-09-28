"""Find worker against a real Postgres (CI service or `make db-up`). Skips if no database."""

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import sessionmaker

from app.db import models  # noqa: F401
from app.db.base import Base
from app.db.enums import CompanyState, JobStatus, Platform, RunStatus, Tier
from app.db.models import Company, Job, JobEvent, Run
from tests.conftest import get_test_db_url, with_retries
from workers.finder import run_find

FIX = Path(__file__).resolve().parents[1] / "fixtures"
NOW = datetime(2026, 9, 28, 3, 0, tzinfo=UTC)


class FakeFetcher:
    def get_json(self, url, params=None):
        return json.loads((FIX / "greenhouse_jobs.json").read_text())


@pytest.fixture
def db():
    engine = create_engine(get_test_db_url())

    def _prep():
        with engine.connect() as c:
            c.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            c.commit()
        Base.metadata.drop_all(engine)
        Base.metadata.create_all(engine)

    with_retries(_prep)
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    session.add(
        Company(
            name="AcmePay",
            tier=Tier.PREMIUM,
            state=CompanyState.ACTIVE,
            platform=Platform.GREENHOUSE,
            platform_board_id="acmepay",
        )
    )
    session.commit()
    yield session
    session.close()
    Base.metadata.drop_all(engine)


def test_find_saves_jobs_then_dedupes(db):
    run = run_find(db, FakeFetcher(), now=NOW)
    assert run.status is RunStatus.OK and run.counts["kept"] == 2 and run.counts["filtered"] == 2
    jobs = db.scalars(select(Job)).all()
    assert len(jobs) == 4
    assert {j.status for j in jobs} == {JobStatus.DISCOVERED, JobStatus.FILTERED_OUT}
    assert db.scalars(select(JobEvent)).all()

    second = run_find(db, FakeFetcher(), now=NOW)
    assert second.counts["duplicates"] == 4 and len(db.scalars(select(Job)).all()) == 4


def test_run_lock(db):
    db.add(Run(kind="find", trigger="manual", status=RunStatus.RUNNING, counts={}))
    db.commit()
    assert run_find(db, FakeFetcher(), now=NOW) is None
