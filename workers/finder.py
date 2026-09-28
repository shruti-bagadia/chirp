"""Find run: read every active company's board, dedupe, pre-filter, and save new jobs."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.connectors.base import ConnectorError, Fetcher
from app.connectors.registry import connector_for
from app.db.enums import Actor, CompanyState, JobStatus, RunKind, RunStatus, RunTrigger, WorkMode
from app.db.models import CompanyStatsDaily, Job, JobEvent, Run
from app.services.companies import scan_order
from app.services.finder import CompanyRef, process_postings
from app.services.schedule import IST
from app.services.states import check_transition

log = logging.getLogger("chirp.finder")


def start_run(db: Session, kind: RunKind, trigger: RunTrigger) -> Run | None:
    """Take the run lock. Returns None if a run of this kind is already going."""
    run = Run(kind=kind, trigger=trigger, status=RunStatus.RUNNING, counts={})
    db.add(run)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return None
    return run


def _save_jobs(db: Session, new_jobs) -> None:
    for nj in new_jobs:
        job = Job(
            company_id=nj.company_id,
            external_id=nj.external_id,
            url=nj.url,
            apply_url=nj.apply_url,
            canonical_url=nj.canonical_url,
            dedupe_key=nj.dedupe_key,
            title=nj.title,
            location=nj.location,
            description=nj.description,
            work_mode=WorkMode(nj.work_mode),
            posted_at=nj.posted_at,
            salary_min_lpa=nj.salary_min_lpa,
            salary_max_lpa=nj.salary_max_lpa,
            experience_min=nj.experience_min,
            experience_max=nj.experience_max,
            status=JobStatus.DISCOVERED,
            flags=nj.flags,
            batch=nj.batch,
        )
        db.add(job)
        db.flush()
        db.add(
            JobEvent(
                job_id=job.id, from_status=None, to_status=JobStatus.DISCOVERED, actor=Actor.FINDER
            )
        )
        if nj.status == JobStatus.FILTERED_OUT:
            t = check_transition(
                JobStatus.DISCOVERED, JobStatus.FILTERED_OUT, Actor.PROCESSOR, nj.status_reason
            )
            job.status, job.status_reason = t.to_status, t.note
            db.add(
                JobEvent(
                    job_id=job.id,
                    from_status=t.from_status,
                    to_status=t.to_status,
                    actor=t.actor,
                    note=t.note,
                )
            )


def _bump_stats(db: Session, company_id, now: datetime, found: int, matched: int) -> None:
    day = now.astimezone(IST).date()
    row = db.scalar(
        select(CompanyStatsDaily).where(
            CompanyStatsDaily.company_id == company_id, CompanyStatsDaily.day == day
        )
    )
    if row is None:
        row = CompanyStatsDaily(
            company_id=company_id,
            day=day,
            jobs_found=0,
            jobs_matched=0,
            jobs_approved=0,
            jobs_applied=0,
        )
        db.add(row)
    row.jobs_found += found
    row.jobs_matched += matched


def run_find(
    db: Session,
    fetcher: Fetcher,
    *,
    trigger: RunTrigger = RunTrigger.SCHEDULE,
    now: datetime | None = None,
) -> Run | None:
    now = now or datetime.now(UTC)
    run = start_run(db, RunKind.FIND, trigger)
    if run is None:
        log.info("find already running; skipping")
        return None

    counts = {
        "companies": 0,
        "found": 0,
        "duplicates": 0,
        "kept": 0,
        "filtered": 0,
        "errors": 0,
        "skipped": 0,
    }
    seen_urls = set(db.scalars(select(Job.canonical_url)))
    seen_keys = set(db.scalars(select(Job.dedupe_key)))
    try:
        for company in scan_order(db):
            connector = connector_for(company.platform)
            if connector is None or not company.platform_board_id:
                counts["skipped"] += 1
                continue
            counts["companies"] += 1
            try:
                postings = connector.fetch(company.platform_board_id, fetcher)
            except ConnectorError as exc:
                company.consecutive_failures += 1
                counts["errors"] += 1
                log.warning(
                    "board failed: %s", exc, extra={"company": company.name, "run_id": str(run.id)}
                )
                db.commit()
                continue
            ref = CompanyRef(
                company.id, company.name, company.tier, company.state == CompanyState.BLOCKED
            )
            outcome = process_postings(
                ref, postings, seen_urls=seen_urls, seen_keys=seen_keys, now=now
            )
            _save_jobs(db, outcome.jobs)
            company.consecutive_failures = 0
            if outcome.kept:
                company.last_match_at = now
            _bump_stats(db, company.id, now, len(postings), outcome.kept)
            db.commit()
            counts["found"] += len(postings)
            counts["duplicates"] += outcome.duplicates
            counts["kept"] += outcome.kept
            counts["filtered"] += outcome.filtered
        run.status = RunStatus.PARTIAL if counts["errors"] else RunStatus.OK
    except Exception as exc:  # record, then re-raise so CI/Actions shows the failure
        db.rollback()
        run.status, run.error = RunStatus.FAILED, repr(exc)
        raise
    finally:
        run.counts, run.finished_at = counts, datetime.now(UTC)
        db.merge(run)
        db.commit()
        log.info("find finished", extra={"run_id": str(run.id)})
    return run
