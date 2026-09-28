import json
from datetime import UTC, datetime
from pathlib import Path

from app.connectors import greenhouse, lever
from app.connectors.base import RawPosting
from app.services.ctc import Tier
from app.services.finder import CompanyRef, batch_label, process_postings
from app.services.states import JobStatus

FIX = Path(__file__).resolve().parents[1] / "fixtures"
NOW = datetime(2026, 9, 28, 3, 0, tzinfo=UTC)  # Monday 08:30 IST


def run(postings, company=None, seen_urls=None, seen_keys=None):
    return process_postings(
        company or CompanyRef(id=1, name="AcmePay", tier=Tier.PREMIUM),
        postings,
        seen_urls=seen_urls if seen_urls is not None else set(),
        seen_keys=seen_keys if seen_keys is not None else set(),
        now=NOW,
    )


def test_greenhouse_board_end_to_end():
    out = run(greenhouse.parse(json.loads((FIX / "greenhouse_jobs.json").read_text())))
    by_title = {j.title: j for j in out.jobs}
    backend = by_title["Backend Engineer II (Python)"]
    assert backend.status is JobStatus.DISCOVERED and backend.work_mode == "hybrid"
    assert (backend.experience_min, backend.experience_max) == (2, 4)
    assert "gh_src" not in backend.canonical_url
    assert by_title["Senior Frontend Engineer"].status is JobStatus.FILTERED_OUT
    assert by_title["Staff Platform Engineer"].status is JobStatus.FILTERED_OUT
    ai = by_title["AI Engineer, Document Intelligence"]
    assert ai.status is JobStatus.DISCOVERED and ai.work_mode == "remote"
    assert out.kept == 2 and out.filtered == 2 and backend.batch == "2026-09-28 AM"


def test_lever_board_end_to_end():
    out = run(
        lever.parse(json.loads((FIX / "lever_postings.json").read_text())),
        CompanyRef(id=2, name="FinLoop", tier=Tier.STANDARD),
    )
    by_title = {j.title: j for j in out.jobs}
    assert by_title["Software Engineer - Backend"].status is JobStatus.DISCOVERED
    assert by_title["Software Engineer - Backend"].work_mode == "hybrid"
    contract = by_title["Backend Developer (Contract)"]
    assert contract.status is JobStatus.FILTERED_OUT and "contract" in contract.status_reason
    low_pay = by_title["Python Engineer"]
    assert low_pay.status is JobStatus.FILTERED_OUT and "floor" in low_pay.status_reason


def test_onsite_flag_carried():
    p = RawPosting(
        "1",
        "Python Developer",
        "https://x.com/j/1",
        "Pune",
        "Work from office. 2 years.",
        posted_at=NOW,
    )
    job = run([p]).jobs[0]
    assert (
        job.status is JobStatus.DISCOVERED and job.flags == ["onsite"] and job.work_mode == "onsite"
    )


def test_dedupe_against_existing_and_within_batch():
    p1 = RawPosting(
        "1", "Backend Engineer", "https://x.com/jobs/1?utm_source=a", "Pune (Hybrid)", posted_at=NOW
    )
    p2 = RawPosting("2", "Backend Engineer", "https://x.com/jobs/1", "Pune (Hybrid)", posted_at=NOW)
    repost = RawPosting(
        "3", "Backend Engineer", "https://x.com/jobs/99", "Pune, India", posted_at=NOW
    )
    seen_urls, seen_keys = set(), set()
    first = run([p1, p2, repost], seen_urls=seen_urls, seen_keys=seen_keys)
    assert len(first.jobs) == 1 and first.duplicates == 2
    again = run([p1], seen_urls=seen_urls, seen_keys=seen_keys)
    assert again.jobs == [] and again.duplicates == 1


def test_blocked_company_everything_filtered():
    p = RawPosting("1", "Backend Engineer", "https://x.com/j/1", "Pune (Hybrid)", posted_at=NOW)
    out = run([p], CompanyRef(id=3, name="Poonawalla Fincorp", blocked=True))
    assert (
        out.jobs[0].status is JobStatus.FILTERED_OUT
        and out.jobs[0].status_reason == "Company is blocked"
    )


def test_postings_without_url_or_title_skipped():
    assert run([RawPosting("1", "", "https://x.com/1"), RawPosting("2", "Backend", "")]).jobs == []


def test_batch_label_pm():
    assert batch_label(datetime(2026, 9, 28, 8, 0, tzinfo=UTC)) == "2026-09-28 PM"
