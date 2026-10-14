"""Machine API (app/api/v1.py) end to end over HTTP, backed by a real Postgres database.

No prior coverage existed for this router at all — these tests focus on the two endpoints
added to push data to production over HTTPS when a direct DB connection isn't available
(/answers/seed, /settings/ctc-floor), plus the pre-existing /profile push/get.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings
from app.core.defaults import DEFAULT_SETTINGS
from app.db import models  # noqa: F401
from app.db.base import Base
from app.db.enums import CompanyState, JobStatus, Platform, Tier
from app.db.models import Answer, AppSettings, Company, Job
from app.db.session import get_db
from tests.conftest import get_test_db_url, with_retries

EXAMPLE_FACTS = yaml.safe_load(
    (Path(__file__).resolve().parents[2] / "profile.example" / "facts.yaml").read_text(
        encoding="utf-8"
    )
)

TOKEN = "test-machine-api-token"


@pytest.fixture
def db_engine():
    engine = create_engine(get_test_db_url())

    def _prep():
        with engine.connect() as c:
            c.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            c.commit()
        Base.metadata.drop_all(engine)
        Base.metadata.create_all(engine)

    with_retries(_prep)
    yield engine
    Base.metadata.drop_all(engine)


@pytest.fixture
def db(db_engine):
    session = sessionmaker(bind=db_engine, expire_on_commit=False)()
    yield session
    session.close()


@pytest.fixture
def client(db_engine, monkeypatch):
    monkeypatch.setenv("CHIRP_API_TOKEN", TOKEN)
    get_settings.cache_clear()
    from app.main import create_app

    app = create_app()

    def _get_db():
        session = sessionmaker(bind=db_engine, expire_on_commit=False)()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = _get_db
    c = TestClient(app)
    c.headers["Authorization"] = f"Bearer {TOKEN}"
    yield c
    get_settings.cache_clear()


def test_profile_push_then_get(client):
    res = client.post("/api/v1/profile", json={"facts": EXAMPLE_FACTS, "note": "test"})
    assert res.status_code == 200 and res.json() == {"version": 1}

    res = client.get("/api/v1/profile")
    assert res.status_code == 200
    assert res.json()["identity"]["name"] == EXAMPLE_FACTS["identity"]["name"]


def test_answers_seed(client, db):
    res = client.post(
        "/api/v1/answers/seed",
        json={
            "answers": [
                {"question": "What's your notice period?", "answer": "15 days"},
                {
                    "question": "Greatest weakness?",
                    "answer": "I over-prepare for meetings.",
                    "category": "behavioral",
                    "type": "personal",
                },
            ]
        },
    )
    assert res.status_code == 200 and res.json() == {"saved": 2}
    assert db.query(Answer).count() == 2


def test_answers_seed_empty_list_is_a_noop(client):
    res = client.post("/api/v1/answers/seed", json={"answers": []})
    assert res.status_code == 200 and res.json() == {"saved": 0}


def test_apply_ctc_floor_patches_existing_row(client, db):
    stale = {
        **DEFAULT_SETTINGS,
        "ctc_tiers": {"premium": {"min": 1, "max": 2, "single": 1, "floor": 1}},
    }
    db.add(AppSettings(id=1, data=stale))
    db.commit()

    res = client.post("/api/v1/settings/ctc-floor")
    assert res.status_code == 200
    body = res.json()
    assert body["patched"] is True
    assert body["after"] == DEFAULT_SETTINGS["ctc_tiers"]

    db.expire_all()
    row = db.get(AppSettings, 1)
    assert row.data["ctc_tiers"] == DEFAULT_SETTINGS["ctc_tiers"]
    assert row.data["fit_threshold"] == stale["fit_threshold"]  # untouched


def test_apply_ctc_floor_with_no_settings_row_yet(client):
    res = client.post("/api/v1/settings/ctc-floor")
    assert res.status_code == 200 and res.json()["patched"] is False


def test_recent_jobs_shows_status_and_reason(client, db):
    company = Company(
        name="Mastercard", tier=Tier.PREMIUM, state=CompanyState.ACTIVE, platform=Platform.WORKDAY
    )
    db.add(company)
    db.commit()
    job = Job(
        company_id=company.id,
        url="https://example.com/job/1",
        canonical_url="https://example.com/job/1",
        dedupe_key="key-1",
        title="Backend Engineer",
        status=JobStatus.FILTERED_OUT,
        status_reason="Score below threshold",
        fit_score=55,
    )
    db.add(job)
    db.commit()

    res = client.get("/api/v1/debug/recent-jobs")
    assert res.status_code == 200
    jobs = res.json()["jobs"]
    assert len(jobs) == 1
    assert jobs[0]["title"] == "Backend Engineer"
    assert jobs[0]["company"] == "Mastercard"
    assert jobs[0]["status"] == "filtered_out"
    assert jobs[0]["status_reason"] == "Score below threshold"
    assert jobs[0]["fit_score"] == 55


@pytest.mark.parametrize(
    "method,path,json_body",
    [
        ("post", "/api/v1/profile", {"facts": EXAMPLE_FACTS}),
        ("get", "/api/v1/profile", None),
        ("post", "/api/v1/answers/seed", {"answers": []}),
        ("post", "/api/v1/settings/ctc-floor", None),
        ("get", "/api/v1/debug/recent-jobs", None),
    ],
)
def test_endpoints_require_token(client, method, path, json_body):
    client.headers.pop("Authorization", None)
    res = (
        getattr(client, method)(path, json=json_body)
        if json_body is not None
        else getattr(client, method)(path)
    )
    assert res.status_code == 401
