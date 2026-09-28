"""Process worker against a real Postgres, with a mock LLM and local storage."""

import shutil
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import sessionmaker

from app.db import models  # noqa: F401
from app.db.base import Base
from app.db.enums import CompanyState, JobStatus, Platform, Tier
from app.db.models import Company, Job, TailoredDocument
from app.llm.client import LLMClient
from app.llm.mock import MockProvider
from app.llm.pii import Redactor
from app.llm.ratelimit import DailyBudget, MemoryUsage, TokenBucket
from app.profile.model import Profile
from app.storage import LocalStorage
from tests.conftest import get_test_db_url, with_retries
from tests.unit.test_processor import SCORE, TAILOR
from workers.processor import run_process

PROFILE = Profile.load(Path(__file__).resolve().parents[2] / "profile.example" / "facts.yaml")
pytestmark = pytest.mark.skipif(
    not (shutil.which("pdflatex") or shutil.which("tectonic")), reason="no LaTeX"
)


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
    s = sessionmaker(bind=engine, expire_on_commit=False)()
    c = Company(
        name="Globex", tier=Tier.STANDARD, state=CompanyState.ACTIVE, platform=Platform.LEVER
    )
    s.add(c)
    s.flush()
    for i, title in enumerate(["Backend Engineer", "Python Developer"]):
        s.add(
            Job(
                company_id=c.id,
                url=f"https://x.com/{i}",
                canonical_url=f"https://x.com/{i}",
                dedupe_key=f"k{i}",
                title=title,
                location="Pune",
                description="Python FastAPI",
                status=JobStatus.DISCOVERED,
                posted_at=datetime.now(UTC),
            )
        )
    s.commit()
    yield s
    s.close()
    Base.metadata.drop_all(engine)


def test_process_moves_jobs_and_saves_documents(db, tmp_path):
    weak = {**SCORE, "score": 40}
    client = LLMClient(
        MockProvider([SCORE, TAILOR, weak]),
        Redactor(PROFILE.identity),
        TokenBucket(1000),
        DailyBudget(100, MemoryUsage()),
        sleep=lambda s: None,
    )
    counts = run_process(db, client=client, storage=LocalStorage(tmp_path), profile=PROFILE)
    assert counts["nest"] == 1 and counts["filtered"] == 1
    doc = db.scalar(select(TailoredDocument))
    assert (tmp_path / doc.resume_pdf_path).read_bytes().startswith(b"%PDF")
    assert {j.status for j in db.scalars(select(Job))} == {
        JobStatus.PENDING_REVIEW,
        JobStatus.FILTERED_OUT,
    }
