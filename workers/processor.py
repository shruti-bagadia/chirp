"""Process run: score and tailor discovered jobs, up to the per-run cap and daily LLM budget."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.defaults import DEFAULT_SETTINGS
from app.db.enums import Actor, JobStatus, RunKind, RunStatus, RunTrigger
from app.db.models import AppSettings, Company, Job, JobEvent, ProfileVersion, TailoredDocument
from app.llm.base import BudgetExhausted
from app.llm.client import LLMClient
from app.llm.factory import make_provider
from app.llm.pii import Redactor
from app.llm.ratelimit import DailyBudget, TokenBucket
from app.llm.usage_db import DbUsage
from app.profile.model import Profile
from app.services import scoring, tailoring
from app.services.ctc import Tier, TierBand
from app.services.processor import process_job
from app.services.states import check_transition
from app.storage import Storage, make_storage
from workers.finder import start_run

log = logging.getLogger("chirp.processor")


def load_profile(db: Session, fallback_path: str | Path = "profile/facts.yaml") -> Profile:
    row = db.scalar(select(ProfileVersion).order_by(ProfileVersion.version.desc()))
    if row is not None:
        return Profile.from_dict(row.facts, version=row.version)
    return Profile.load(fallback_path)


def _move(db: Session, job: Job, to: JobStatus, note: str | None = None) -> None:
    t = check_transition(job.status, to, Actor.PROCESSOR, note)
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


def run_process(
    db: Session,
    *,
    client: LLMClient | None = None,
    storage: Storage | None = None,
    profile: Profile | None = None,
    trigger: RunTrigger = RunTrigger.SCHEDULE,
) -> dict | None:
    s = get_settings()
    run = start_run(db, RunKind.PROCESS, trigger)
    if run is None:
        return None
    counts = {"processed": 0, "nest": 0, "filtered": 0, "errors": 0, "stopped_for_budget": False}
    try:
        row = db.get(AppSettings, 1)
        cfg = row.data if row else DEFAULT_SETTINGS
        profile = profile or load_profile(db)
        storage = storage or make_storage(s)
        if client is None:
            client = LLMClient(
                make_provider(s),
                Redactor(profile.identity),
                TokenBucket(s.llm_requests_per_minute),
                DailyBudget(s.llm_daily_request_budget, DbUsage(db, s.llm_provider)),
            )
        jobs = db.scalars(
            select(Job)
            .join(Company)
            .where(Job.status == JobStatus.DISCOVERED)
            .order_by(Company.priority_score.desc(), Job.posted_at.desc().nullslast())
            .limit(cfg["max_jobs_per_run"])
        ).all()
        for job in jobs:
            band = TierBand(**cfg["ctc_tiers"][Tier(job.company.tier).value])
            try:
                result = process_job(
                    scoring.JobForLLM(
                        job.title,
                        job.company.name,
                        job.location,
                        job.work_mode.value,
                        job.description,
                    ),
                    profile=profile,
                    client=client,
                    band=band,
                    salary=(
                        float(job.salary_min_lpa) if job.salary_min_lpa is not None else None,
                        float(job.salary_max_lpa) if job.salary_max_lpa is not None else None,
                    ),
                    threshold=cfg["fit_threshold"],
                )
            except BudgetExhausted:
                counts["stopped_for_budget"] = True
                break
            counts["processed"] += 1
            job.attempts += 1
            if result.score:
                job.fit_score = result.final_score
                job.fit_summary = result.score.summary
                job.fit_gaps = result.score.gaps
                job.fit_matches = result.score.must_haves_matched
                job.role_focus = result.score.role_focus
            job.flags = sorted(set(job.flags or []) | set(result.flags))
            if result.status == JobStatus.PENDING_REVIEW:
                path = f"resumes/{job.id}.pdf"
                storage.put(path, result.resume.pdf)
                job.expected_ctc_lpa = result.expected_ctc
                db.add(
                    TailoredDocument(
                        job_id=job.id,
                        resume_pdf_path=path,
                        resume_tex=result.resume.tex,
                        selection={
                            k: [b.fact_id for b in v]
                            for k, v in result.resume.draft.experience.items()
                        },
                        change_summary=result.resume.draft.change_summary,
                        cover_letter=result.cover_letter,
                        fabrication_check={
                            "passed": True,
                            "dropped_for_length": result.resume.dropped,
                        },
                        profile_version=profile.version,
                        prompt_version=f"{scoring.PROMPT_VERSION}+{tailoring.PROMPT_VERSION}",
                    )
                )
                _move(db, job, JobStatus.PENDING_REVIEW)
                counts["nest"] += 1
            elif result.status == JobStatus.FILTERED_OUT:
                _move(db, job, JobStatus.FILTERED_OUT, result.reason)
                counts["filtered"] += 1
            else:
                note = result.reason
                if result.fabrication_failures:
                    note += ": " + "; ".join(result.fabrication_failures[:5])
                _move(db, job, JobStatus.ERROR, note)
                counts["errors"] += 1
            db.commit()
        run.status = (
            RunStatus.PARTIAL if counts["errors"] or counts["stopped_for_budget"] else RunStatus.OK
        )
    except Exception as exc:
        db.rollback()
        run.status, run.error = RunStatus.FAILED, repr(exc)
        raise
    finally:
        run.counts, run.finished_at = counts, datetime.now(UTC)
        if client is not None:
            run.llm_requests = client.stats.requests
        db.merge(run)
        db.commit()
    return counts
