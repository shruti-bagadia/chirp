from app.db import models  # noqa: F401
from app.db.base import Base


def test_all_tables_registered():
    expected = {
        "companies",
        "jobs",
        "job_events",
        "tailored_documents",
        "answers",
        "question_variants",
        "application_answers",
        "profile_versions",
        "settings",
        "runs",
        "run_requests",
        "applier_heartbeat",
        "llm_usage",
        "company_stats_daily",
    }
    assert expected <= set(Base.metadata.tables)


def test_job_urls_and_dedupe_keys_unique():
    jobs = Base.metadata.tables["jobs"]
    assert jobs.c.canonical_url.unique and jobs.c.dedupe_key.unique
