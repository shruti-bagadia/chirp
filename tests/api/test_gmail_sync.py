"""Gmail sync orchestration against a real Postgres, with a fake Gmail client
(the real `GmailClient` needs live OAuth — see app/connectors/gmail_alerts.py).
"""

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import sessionmaker

from app.connectors.gmail_alerts import AlertEmail
from app.db import models  # noqa: F401
from app.db.base import Base
from app.db.enums import CompanyCategory, CompanySource, CompanyState, Tier
from app.db.models import Company
from app.services.companies import add_candidate_from_email, find_by_name
from tests.conftest import get_test_db_url, with_retries
from workers.gmail_sync import run_gmail_sync


class FakeGmailClient:
    def __init__(self, emails: list[AlertEmail]) -> None:
        self._emails = emails

    def list_alert_emails(self, label: str) -> list[AlertEmail]:
        return self._emails


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


def test_add_candidate_from_email_creates_candidate(db):
    c = add_candidate_from_email(db, "Quantum Systems")
    assert c is not None
    assert c.state == CompanyState.CANDIDATE and c.source == CompanySource.EMAIL_ALERT


def test_add_candidate_from_email_skips_known_company(db):
    db.add(Company(name="Mastercard", tier=Tier.PREMIUM, state=CompanyState.ACTIVE))
    db.commit()
    assert add_candidate_from_email(db, "Mastercard") is None
    assert len(db.scalars(select(Company)).all()) == 1


def test_add_candidate_from_email_detects_platform_when_url_given(db):
    c = add_candidate_from_email(db, "Druva", url="https://job-boards.greenhouse.io/druva")
    assert c.platform.value == "greenhouse" and c.state == CompanyState.CANDIDATE


def test_run_gmail_sync_adds_from_links_and_names(db):
    html = """
    <p>Backend Engineer at Acme Fintech.</p>
    <a href="https://boards.greenhouse.io/acme-fintech/jobs/1">apply</a>
    <p>Also: AI Engineer at Riverstone Analytics.</p>
    """
    client = FakeGmailClient([AlertEmail("m1", "New jobs", html)])
    counts = run_gmail_sync(db, client)
    assert counts["emails"] == 1
    assert counts["added_from_links"] == 1
    assert counts["added_from_names"] == 1
    assert find_by_name(db, "Acme Fintech") is not None
    assert find_by_name(db, "Riverstone Analytics") is not None


def test_run_gmail_sync_does_not_double_add_a_company_found_both_ways(db):
    html = """
    <p>Backend Engineer at Acmefintech.</p>
    <a href="https://boards.greenhouse.io/acmefintech/jobs/1">apply</a>
    """
    client = FakeGmailClient([AlertEmail("m1", "New jobs", html)])
    counts = run_gmail_sync(db, client)
    assert counts["added_from_links"] == 1
    assert counts["added_from_names"] == 0  # same name as the link-derived company


def test_run_gmail_sync_skips_already_known_companies(db):
    db.add(
        Company(
            name="Druva",
            tier=Tier.PREMIUM,
            category=CompanyCategory.PRODUCT_SAAS,
            state=CompanyState.ACTIVE,
        )
    )
    db.commit()
    html = '<a href="https://job-boards.greenhouse.io/druva/jobs/1">apply</a>'
    client = FakeGmailClient([AlertEmail("m1", "New jobs", html)])
    counts = run_gmail_sync(db, client)
    assert counts["already_known"] == 1
    assert counts["added_from_links"] == 0
    assert len(db.scalars(select(Company)).all()) == 1


def test_run_gmail_sync_ignores_unrecognized_links(db):
    html = (
        '<a href="https://www.linkedin.com/jobs/view/12345">apply</a><p>Role at Some Startup.</p>'
    )
    client = FakeGmailClient([AlertEmail("m1", "New jobs", html)])
    counts = run_gmail_sync(db, client)
    assert counts["added_from_links"] == 0
    assert counts["added_from_names"] == 1
