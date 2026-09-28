"""Nightly worker against a real Postgres. Skips if no database."""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import sessionmaker

from app.db import models  # noqa: F401
from app.db.base import Base
from app.db.enums import CompanyCategory, CompanyState, Platform, RunStatus, Tier
from app.db.models import AppSettings, Company, CompanyStatsDaily, Job, Run
from tests.conftest import get_test_db_url, with_retries
from workers.nightly import recalculate_priority, run_nightly

FIX = Path(__file__).resolve().parents[1] / "fixtures"
NOW = datetime(2026, 9, 28, 3, 0, tzinfo=UTC)


class FakeFetcher:
    def get_json(self, url, params=None):
        return json.loads((FIX / "greenhouse_jobs.json").read_text())

    def close(self) -> None:
        pass


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
    yield session
    session.close()
    Base.metadata.drop_all(engine)


def test_run_lock(db):
    db.add(Run(kind="nightly", trigger="manual", status=RunStatus.RUNNING, counts={}))
    db.commit()
    assert run_nightly(db, now=NOW) is None


def test_recalculate_priority_reflects_tier_and_domain(db):
    premium_fintech = Company(
        name="A",
        tier=Tier.PREMIUM,
        category=CompanyCategory.BANKING_FINTECH,
        state=CompanyState.ACTIVE,
    )
    services = Company(
        name="B",
        tier=Tier.SERVICES,
        category=CompanyCategory.SERVICES_CONSULTING,
        state=CompanyState.ACTIVE,
    )
    db.add_all([premium_fintech, services])
    db.commit()
    hi = recalculate_priority(db, premium_fintech, NOW)
    lo = recalculate_priority(db, services, NOW)
    assert hi > lo
    assert 0 <= hi <= 100 and 0 <= lo <= 100


def test_recalculate_priority_rewards_recent_activity_and_approvals(db):
    company = Company(name="C", tier=Tier.STANDARD, state=CompanyState.ACTIVE)
    db.add(company)
    db.commit()
    baseline = recalculate_priority(db, company, NOW)

    db.add(
        CompanyStatsDaily(
            company_id=company.id,
            day=NOW.date(),
            jobs_found=10,
            jobs_matched=5,
            jobs_approved=5,
            jobs_applied=2,
        )
    )
    db.commit()
    with_activity = recalculate_priority(db, company, NOW)
    assert with_activity > baseline


def test_stale_active_company_goes_dormant(db):
    c = Company(
        name="Stale Co",
        tier=Tier.STANDARD,
        state=CompanyState.ACTIVE,
        last_match_at=NOW - timedelta(days=90),
    )
    db.add(c)
    db.commit()
    counts = run_nightly(db, now=NOW)
    assert counts["went_dormant"] == 1
    db.refresh(c)
    assert c.state == CompanyState.DORMANT


def test_recently_active_company_stays_active(db):
    c = Company(
        name="Fresh Co",
        tier=Tier.STANDARD,
        state=CompanyState.ACTIVE,
        last_match_at=NOW - timedelta(days=5),
    )
    db.add(c)
    db.commit()
    run_nightly(db, now=NOW)
    db.refresh(c)
    assert c.state == CompanyState.ACTIVE


def test_dormant_company_reactivates_on_a_real_match(db):
    # "greenhouse" is already registered in app.connectors.registry with a real
    # GreenhouseConnector — no need to fake it, only the HTTP layer below.
    c = Company(
        name="AcmePay",
        tier=Tier.PREMIUM,
        state=CompanyState.DORMANT,
        platform=Platform.GREENHOUSE,
        platform_board_id="acmepay",
        last_match_at=NOW - timedelta(days=90),
    )
    db.add(c)
    db.commit()

    from unittest.mock import patch

    with patch("app.connectors.http.HttpFetcher", FakeFetcher):
        counts = run_nightly(db, now=NOW)

    assert counts["rechecked"] == 1 and counts["reactivated"] == 1
    db.refresh(c)
    assert c.state == CompanyState.ACTIVE
    assert db.scalars(select(Job).where(Job.company_id == c.id)).all()


def test_dormant_company_without_a_board_id_is_skipped(db):
    c = Company(name="Unknown Co", tier=Tier.STANDARD, state=CompanyState.DORMANT)
    db.add(c)
    db.commit()
    counts = run_nightly(db, now=NOW)
    assert counts["rechecked"] == 1 and counts["reactivated"] == 0
    db.refresh(c)
    assert c.state == CompanyState.DORMANT


def test_dormant_after_days_setting_is_respected(db):
    row = AppSettings(id=1, data={"dormant_after_days": 10})
    db.add(row)
    c = Company(
        name="Barely Active",
        tier=Tier.STANDARD,
        state=CompanyState.ACTIVE,
        last_match_at=NOW - timedelta(days=15),
    )
    db.add(c)
    db.commit()
    run_nightly(db, now=NOW)
    db.refresh(c)
    assert c.state == CompanyState.DORMANT
