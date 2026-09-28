"""Nightly upkeep: recalculate company priority scores, mark inactive companies
dormant, and give dormant companies an occasional re-check in case they've started
hiring again. See docs/08_company_registry.md §1 and §4.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.connectors.base import ConnectorError, Fetcher
from app.connectors.registry import connector_for
from app.core.defaults import DEFAULT_SETTINGS
from app.db.enums import CompanyCategory, CompanyState, RunKind, RunStatus, RunTrigger, WorkMode
from app.db.models import AppSettings, Company, CompanyStatsDaily, Job
from app.services.finder import CompanyRef, process_postings
from app.services.schedule import IST
from workers.finder import _bump_stats, _save_jobs, start_run

log = logging.getLogger("chirp.nightly")

# Priority score (0-100): weights from docs/08_company_registry.md §4. Stack fit and
# location fit are approximated from already-scored jobs (title/role_focus/work_mode)
# rather than re-parsing descriptions from scratch — that data already exists once a
# job's been through `chirp process`.
_TIER_SCORE = {"premium": 25, "standard": 18, "services": 10}
_DOMAIN_FIT = {
    CompanyCategory.BANKING_FINTECH: 20,
    CompanyCategory.AI_FIRST: 20,
    CompanyCategory.PRODUCT_SAAS: 14,
    CompanyCategory.SERVICES_CONSULTING: 8,
}
_STACK_WORDS = ("python", "fastapi", "llm", "genai", "generative ai", "ai", "ml", "backend")
_LOOKBACK_DAYS = 30


def _stack_fit_score(db: Session, company_id, since: datetime) -> int:
    rows = db.execute(
        select(Job.title, Job.role_focus).where(
            Job.company_id == company_id, Job.created_at >= since
        )
    ).all()
    if not rows:
        return 0
    hits = sum(
        1
        for title, role_focus in rows
        if any(w in f"{title or ''} {role_focus or ''}".lower() for w in _STACK_WORDS)
    )
    return round(20 * hits / len(rows))


def _location_fit_score(db: Session, company_id, since: datetime) -> int:
    rows = db.scalars(
        select(Job.work_mode).where(Job.company_id == company_id, Job.created_at >= since)
    ).all()
    if not rows:
        return 0
    good = sum(1 for w in rows if w in (WorkMode.HYBRID, WorkMode.REMOTE))
    return round(15 * good / len(rows))


def _sum_stat(db: Session, company_id, field, since_day) -> int:
    return (
        db.scalar(
            select(func.sum(field)).where(
                CompanyStatsDaily.company_id == company_id, CompanyStatsDaily.day >= since_day
            )
        )
        or 0
    )


def _activity_score(db: Session, company_id, since_day) -> int:
    matched = _sum_stat(db, company_id, CompanyStatsDaily.jobs_matched, since_day)
    return round(10 * min(1.0, matched / 5))  # 5+ matches in the window = full marks


def _approval_score(db: Session, company_id, since_day) -> int:
    matched = _sum_stat(db, company_id, CompanyStatsDaily.jobs_matched, since_day)
    if matched == 0:
        return 5  # no history yet: neutral, not a penalty
    approved = _sum_stat(db, company_id, CompanyStatsDaily.jobs_approved, since_day)
    return round(10 * min(1.0, approved / matched))


def recalculate_priority(db: Session, company: Company, now: datetime) -> int:
    """0-100. Pin High/Low overrides are applied at display/scan time (see
    `app.services.companies.scan_order`), not baked into the stored score itself."""
    since_dt = now - timedelta(days=_LOOKBACK_DAYS)
    since_day = since_dt.astimezone(IST).date()
    score = _TIER_SCORE.get(company.tier.value, 15)
    score += _DOMAIN_FIT.get(company.category, 10) if company.category else 10
    score += _stack_fit_score(db, company.id, since_dt)
    score += _location_fit_score(db, company.id, since_dt)
    score += _activity_score(db, company.id, since_day)
    score += _approval_score(db, company.id, since_day)
    return max(0, min(100, score))


def _recheck_dormant(db: Session, company: Company, fetcher: Fetcher, now: datetime) -> bool:
    """Fetches the board once; if anything survives the pre-filter, saves those jobs
    and reactivates the company. Returns whether it was reactivated."""
    connector = connector_for(company.platform)
    if connector is None or not company.platform_board_id:
        return False
    try:
        postings = connector.fetch(company.platform_board_id, fetcher)
    except ConnectorError as exc:
        log.warning("dormant re-check failed: %s", exc, extra={"company": company.name})
        return False
    seen_urls = set(db.scalars(select(Job.canonical_url)))
    seen_keys = set(db.scalars(select(Job.dedupe_key)))
    ref = CompanyRef(company.id, company.name, company.tier, blocked=False)
    outcome = process_postings(ref, postings, seen_urls=seen_urls, seen_keys=seen_keys, now=now)
    if not outcome.kept:
        return False
    _save_jobs(db, outcome.jobs)
    _bump_stats(db, company.id, now, len(postings), outcome.kept)
    company.state = CompanyState.ACTIVE
    company.last_match_at = now
    company.consecutive_failures = 0
    return True


def run_nightly(
    db: Session, *, trigger: RunTrigger = RunTrigger.SCHEDULE, now: datetime | None = None
) -> dict | None:
    now = now or datetime.now(UTC)
    run = start_run(db, RunKind.NIGHTLY, trigger)
    if run is None:
        log.info("nightly already running; skipping")
        return None

    counts = {"rescored": 0, "went_dormant": 0, "rechecked": 0, "reactivated": 0, "errors": 0}
    row = db.get(AppSettings, 1)
    cfg = row.data if row else DEFAULT_SETTINGS
    dormant_after = timedelta(days=cfg.get("dormant_after_days", 60))
    try:
        for c in db.scalars(select(Company).where(Company.state == CompanyState.ACTIVE)).all():
            c.priority_score = recalculate_priority(db, c, now)
            counts["rescored"] += 1
            last = c.last_match_at or c.created_at
            if now - last > dormant_after:
                c.state = CompanyState.DORMANT
                counts["went_dormant"] += 1
        db.commit()

        from app.connectors.http import HttpFetcher

        fetcher = HttpFetcher()
        try:
            for c in db.scalars(select(Company).where(Company.state == CompanyState.DORMANT)).all():
                counts["rechecked"] += 1
                try:
                    if _recheck_dormant(db, c, fetcher, now):
                        counts["reactivated"] += 1
                except Exception:
                    counts["errors"] += 1
                    log.exception("dormant re-check errored", extra={"company": c.name})
                db.commit()
        finally:
            fetcher.close()
        run.status = RunStatus.PARTIAL if counts["errors"] else RunStatus.OK
    except Exception as exc:
        db.rollback()
        run.status, run.error = RunStatus.FAILED, repr(exc)
        raise
    finally:
        run.counts = counts
        run.finished_at = datetime.now(UTC)
        db.merge(run)
        db.commit()
    return counts
