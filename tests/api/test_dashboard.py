"""Dashboard routes end to end over HTTP, backed by a real Postgres database."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings
from app.core.security import hash_password
from app.db import models  # noqa: F401
from app.db.base import Base
from app.db.enums import (
    AnswerCategory,
    AnswerType,
    CompanyState,
    JobStatus,
    ManualApplicationSource,
    Pinned,
    Platform,
    RunKind,
    RunStatus,
    RunTrigger,
    Tier,
)
from app.db.models import Answer, Company, Job, ManualApplication, ProfileVersion, Run
from app.db.session import get_db
from tests.conftest import get_test_db_url, with_retries

EXAMPLE_FACTS = yaml.safe_load(
    (Path(__file__).resolve().parents[2] / "profile.example" / "facts.yaml").read_text(
        encoding="utf-8"
    )
)

PASSWORD = "a horse a battery a staple"


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
def companies(db):
    a = Company(
        name="Mastercard", tier=Tier.PREMIUM, state=CompanyState.ACTIVE, platform=Platform.WORKDAY
    )
    b = Company(
        name="Druva", tier=Tier.PREMIUM, state=CompanyState.ACTIVE, platform=Platform.GREENHOUSE
    )
    db.add_all([a, b])
    db.commit()
    return a, b


@pytest.fixture
def pending_jobs(db, companies):
    a, _ = companies
    jobs = []
    for i in range(8):
        j = Job(
            company_id=a.id,
            url=f"https://example.com/job/{i}",
            canonical_url=f"https://example.com/job/{i}",
            dedupe_key=f"key-{i}",
            title=f"Backend Engineer {i}",
            location="Pune",
            status=JobStatus.PENDING_REVIEW,
            fit_score=90 - i,
            expected_ctc_lpa=20,
        )
        db.add(j)
        jobs.append(j)
    db.commit()
    for j in jobs:
        db.refresh(j)
    return jobs


@pytest.fixture
def question_hand(db, companies):
    """Two jobs blocked on the same new question, at two different companies."""
    a, b = companies
    j1 = Job(
        company_id=a.id,
        url="https://example.com/q1",
        canonical_url="https://example.com/q1",
        dedupe_key="q1",
        title="Backend Engineer",
        location="Pune",
        status=JobStatus.NEEDS_ATTENTION,
        status_reason="question:What's your biggest weakness?",
    )
    j2 = Job(
        company_id=b.id,
        url="https://example.com/q2",
        canonical_url="https://example.com/q2",
        dedupe_key="q2",
        title="Software Engineer",
        location="Pune",
        status=JobStatus.NEEDS_ATTENTION,
        status_reason="question:What's your biggest weakness?",
    )
    db.add_all([j1, j2])
    db.commit()
    return j1, j2


@pytest.fixture
def quick_apply_job(db, companies):
    a, _ = companies
    j = Job(
        company_id=a.id,
        url="https://example.com/quick",
        canonical_url="https://example.com/quick",
        dedupe_key="quick1",
        title="Backend Developer",
        location="Pune",
        status=JobStatus.NEEDS_ATTENTION,
        status_reason="quick_apply",
        expected_ctc_lpa=20,
    )
    db.add(j)
    db.commit()
    db.refresh(j)
    return j


def _override_db(app, engine):
    def _get_db():
        session = sessionmaker(bind=engine, expire_on_commit=False)()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = _get_db


@pytest.fixture
def client(db_engine, monkeypatch):
    monkeypatch.setenv("DASHBOARD_PASSWORD_HASH", hash_password(PASSWORD))
    monkeypatch.setenv("SESSION_SECRET", "test-only-secret")
    get_settings.cache_clear()
    from app.main import create_app

    app = create_app()
    _override_db(app, db_engine)
    c = TestClient(app)
    res = c.post("/login", data={"password": PASSWORD})
    # TestClient follows the 303 redirect, so `res` is the final "/" page (200);
    # the redirect itself is in `res.history`.
    assert res.status_code == 200 and res.history and res.history[0].status_code == 303
    token = re.search(r'name="csrf-token" content="([^"]+)"', res.text)[1]
    c.headers["X-CSRF-Token"] = token
    yield c
    get_settings.cache_clear()


def trig(res):
    return json.loads(res.headers.get("HX-Trigger", "{}"))


def test_login_required(db_engine, monkeypatch):
    monkeypatch.setenv("DASHBOARD_PASSWORD_HASH", hash_password(PASSWORD))
    get_settings.cache_clear()
    from app.main import create_app

    app = create_app()
    _override_db(app, db_engine)
    c = TestClient(app, follow_redirects=False)
    for path in ["/", "/hands", "/flown", "/more"]:
        res = c.get(path)
        assert res.status_code == 303 and res.headers["location"] == "/login"
    get_settings.cache_clear()


def test_wrong_password_shown_error(db_engine, monkeypatch):
    monkeypatch.setenv("DASHBOARD_PASSWORD_HASH", hash_password(PASSWORD))
    get_settings.cache_clear()
    from app.main import create_app

    app = create_app()
    _override_db(app, db_engine)
    c = TestClient(app)
    res = c.post("/login", data={"password": "nope"})
    assert res.status_code == 401 and "Wrong password" in res.text
    get_settings.cache_clear()


def test_pages(client, pending_jobs):
    for path in ["/", "/hands", "/flown", "/more"]:
        assert client.get(path).status_code == 200


def test_bulk_approve_updates_queue_and_counts(client, pending_jobs):
    ids = [j.id for j in pending_jobs[:2]]
    res = client.post("/jobs/bulk", data={"action": "approve", "ids": [str(i) for i in ids]})
    assert res.status_code == 200
    assert trig(res)["chirp:approved"]["count"] == 2
    assert "6</b> in the nest" in res.text


def test_bulk_reject(client, pending_jobs):
    res = client.post("/jobs/bulk", data={"action": "reject", "ids": [str(pending_jobs[0].id)]})
    assert trig(res)["chirp:rejected"]["count"] == 1


def test_bulk_bad_action(client, pending_jobs):
    res = client.post("/jobs/bulk", data={"action": "nope", "ids": [str(pending_jobs[0].id)]})
    assert res.status_code == 400


def test_detail_and_404(client, pending_jobs):
    ok = client.get(f"/jobs/{pending_jobs[0].id}")
    assert ok.status_code == 200 and "Backend Engineer 0" in ok.text and "Matches" in ok.text
    assert client.get("/jobs/00000000-0000-0000-0000-000000000000").status_code == 404


def test_ctc_edit_valid_and_invalid(client, pending_jobs):
    job = pending_jobs[0]
    ok = client.post(f"/jobs/{job.id}/ctc", data={"expected_ctc": "19"})
    assert f"row-ctc-{job.id}" in ok.text and "19" in trig(ok)["chirp:toast"]
    bad = client.post(f"/jobs/{job.id}/ctc", data={"expected_ctc": "abc"})
    assert "between 5 and 80" in bad.text


def test_answer_once_releases_both_jobs(client, question_hand):
    from app.web.db_store import question_hand_id

    hid = question_hand_id("What's your biggest weakness?")
    empty = client.post(f"/hands/{hid}/answer", data={"answer": " "})
    assert empty.headers.get("HX-Retarget") == "#sheet-body"
    ok = client.post(f"/hands/{hid}/answer", data={"answer": "I over-polish.", "save": "true"})
    assert "chirp:close-sheet" in trig(ok)
    assert f"hand-{hid}" not in ok.text


def test_quick_apply_marks_flown(client, quick_apply_job):
    res = client.post(f"/hands/{quick_apply_job.id}/applied")
    assert "chirp:celebrate" in trig(res)
    assert "Mastercard" in client.get("/flown").text


def test_schedule_add_invalid_time(client, pending_jobs):
    res = client.post("/settings/schedule/add", data={"step": "find", "time": "25:00"})
    assert "valid time" in res.text


def test_pause_from_strip_and_schedule(client, pending_jobs):
    a = client.post("/settings/pause")
    assert "Chirp is resting" in a.text
    b = client.post("/settings/pause", headers={"HX-Target": "schedule"})
    assert 'id="runstrip"' in b.text


def test_run_lock_is_per_kind(client, db, companies):
    """Real per-kind lock (docs: 'one run of each kind at a time'), not one lock
    shared across every kind."""
    first = client.post("/runs/find")
    second = client.post("/runs/apply")
    assert "looking" in trig(first)["chirp:toast"]
    assert "taking off" in trig(second)["chirp:toast"]

    db.add(Run(kind=RunKind.FIND, trigger=RunTrigger.MANUAL, status=RunStatus.RUNNING, counts={}))
    db.commit()
    third = client.post("/runs/find")
    assert "Already running" in trig(third)["chirp:toast"]


def test_unknown_run_404(client, pending_jobs):
    assert client.post("/runs/party").status_code == 404


def test_flown_detail_route(client, db, companies):
    a, _ = companies
    j = Job(
        company_id=a.id,
        url="https://example.com/flown1",
        canonical_url="https://example.com/flown1",
        dedupe_key="flown1",
        title="Backend Developer",
        location="Pune",
        status=JobStatus.APPLIED,
        expected_ctc_lpa=18,
    )
    db.add(j)
    db.commit()
    db.refresh(j)
    assert "Open application" in client.get(f"/flown/{j.id}").text
    assert client.get("/flown/00000000-0000-0000-0000-000000000000").status_code == 404


def test_more_page_shows_answers_and_companies(client, companies, db):
    db.add(
        Answer(
            canonical_question="Greatest weakness",
            answer="I over-polish.",
            type=AnswerType.PERSONAL,
            category=AnswerCategory.BEHAVIORAL,
        )
    )
    db.commit()
    res = client.get("/more")
    assert res.status_code == 200
    assert "Greatest weakness" in res.text
    assert "Mastercard" in res.text  # active company from the `companies` fixture


def test_answer_edit_updates_and_closes_sheet(client, db):
    row = Answer(
        canonical_question="Notice period",
        answer="30 days",
        type=AnswerType.FIXED,
        category=AnswerCategory.LOGISTICS,
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    form = client.get(f"/answers/{row.id}")
    assert form.status_code == 200 and "Notice period" in form.text

    res = client.post(f"/answers/{row.id}", data={"answer": "15 days", "short_answer": ""})
    assert "chirp:close-sheet" in trig(res)
    assert "15 days" in res.text

    db.refresh(row)
    assert row.answer == "15 days" and row.version == 2


def test_answer_edit_rejects_empty(client, db):
    row = Answer(
        canonical_question="Strength",
        answer="Ownership",
        type=AnswerType.PERSONAL,
        category=AnswerCategory.BEHAVIORAL,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    res = client.post(f"/answers/{row.id}", data={"answer": " "})
    assert "Write an answer" in res.text


def test_company_candidate_approve_and_block(client, db):
    cand = Company(name="Candidate Co", tier=Tier.STANDARD, state=CompanyState.CANDIDATE)
    db.add(cand)
    db.commit()
    db.refresh(cand)

    res = client.get("/more")
    assert "Candidate Co" in res.text

    approved = client.post(f"/companies/{cand.id}/approve", data={"tier": "premium"})
    assert approved.status_code == 200
    db.refresh(cand)
    assert cand.state == CompanyState.ACTIVE and cand.tier == Tier.PREMIUM

    blocked_id = cand.id
    blocked = client.post(f"/companies/{blocked_id}/block")
    assert blocked.status_code == 200
    db.refresh(cand)
    assert cand.state == CompanyState.BLOCKED


def test_company_pin_cycles(client, companies, db):
    a, _ = companies
    res = client.post(f"/companies/{a.id}/pin", data={"pinned": "high"})
    assert res.status_code == 200
    assert "Mastercard" in res.text
    db.refresh(a)
    assert a.pinned == Pinned.HIGH


def test_company_add_from_url(client):
    res = client.post(
        "/companies",
        data={"url": "https://job-boards.greenhouse.io/exampleco", "tier": "standard"},
    )
    assert res.status_code == 200
    assert "exampleco" in res.text.lower() or "Exampleco" in res.text


def test_company_add_bad_url_shows_error(client, monkeypatch):
    from app.web import db_store

    def boom(*a, **kw):
        raise ValueError("nope")

    monkeypatch.setattr(db_store.DbStore, "add_company", boom)
    res = client.post("/companies", data={"url": "not a url", "tier": "standard"})
    assert "Couldn&#39;t add" in res.text or "Couldn't add" in res.text


# ---------- Tailor (manual/external jobs) ----------


@pytest.fixture
def profile_version(db):
    row = ProfileVersion(version=1, facts=EXAMPLE_FACTS, note="test")
    db.add(row)
    db.commit()
    return row


def test_tailor_generates_resume_and_marks_applied(client, monkeypatch, profile_version):
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    get_settings.cache_clear()
    res = client.post(
        "/tailor",
        data={
            "company": "Acme Bank",
            "title": "Backend Engineer",
            "location": "Pune",
            "mode": "hybrid",
            "tier": "standard",
            "posting_url": "https://example.com/jobs/acme-1",
            "description": "We need a backend engineer with Python and FastAPI experience.",
        },
    )
    get_settings.cache_clear()
    assert res.status_code == 200
    assert "Download resume PDF" in res.text
    assert "I&#39;ve applied" in res.text or "I've applied" in res.text

    m = re.search(r'name="resume_pdf_path" value="([^"]+)"', res.text)
    assert m and m[1]

    res2 = client.post(
        "/tailor/applied",
        data={
            "company": "Acme Bank",
            "title": "Backend Engineer",
            "resume_pdf_path": m[1],
            "cover_letter": "Dear team, I would love to join Acme Bank.",
            "posting_url": "https://example.com/jobs/acme-1",
        },
    )
    assert res2.status_code == 200
    assert "Marked as flown" in res2.text

    res3 = client.get("/flown")
    assert "Acme Bank" in res3.text and "applied by you" in res3.text


def test_tailor_never_filters_on_low_score(client, monkeypatch, profile_version):
    """threshold=0 for manual jobs: a low fit score is shown, never dropped."""
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    get_settings.cache_clear()
    res = client.post(
        "/tailor",
        data={
            "company": "Random Co",
            "title": "Deep Sea Welder",
            "location": "Remote",
            "mode": "remote",
            "tier": "standard",
            "description": "We need someone comfortable welding underwater rigs.",
        },
    )
    get_settings.cache_clear()
    assert res.status_code == 200
    assert "Download resume PDF" in res.text


def test_flown_merges_manual_applications(client, db):
    m = ManualApplication(
        company="Direct Apply Co", title="SDE", source=ManualApplicationSource.DASHBOARD
    )
    db.add(m)
    db.commit()
    res = client.get("/flown")
    assert res.status_code == 200
    assert "Direct Apply Co" in res.text

    detail = client.get(f"/flown/manual:{m.id}")
    assert detail.status_code == 200 and "Direct Apply Co" in detail.text

    cb = client.post(f"/flown/manual:{m.id}/callback")
    assert cb.status_code == 200
    db.refresh(m)
    assert m.got_callback is True
