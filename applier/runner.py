"""Orchestrates one apply run: claim approved jobs, drive each through its
platform's runner, record the outcome. Used by `chirp apply`, `chirp applier
--watch`, and the dashboard's "Fly now" button (same machine, same database, for
now — see the note in docs/03_architecture.md about the laptop/dashboard split
this will need once Chirp is actually deployed).
"""

from __future__ import annotations

import logging
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.config import get_settings
from app.core.defaults import DEFAULT_SETTINGS
from app.db.enums import Actor, JobStatus, RunKind, RunStatus, RunTrigger
from app.db.models import (
    Answer,
    ApplicationAnswer,
    AppSettings,
    Company,
    Job,
    JobEvent,
    ProfileVersion,
)
from app.profile.model import Profile
from app.services.answers import match_question
from app.services.schedule import IST
from app.services.states import check_transition
from app.storage import make_storage
from applier.form_mapper import applicant_from_identity
from applier.runners import ashby, greenhouse, lever
from applier.runners.base import Blocked, detect_blocked, fill_form, looks_submitted, submit_form

log = logging.getLogger("chirp.applier")

RUNNER_CONFIGS = {"greenhouse": greenhouse.CONFIG, "lever": lever.CONFIG, "ashby": ashby.CONFIG}


@dataclass
class ApplyCounts:
    claimed: int = 0
    applied: int = 0
    needs_attention: int = 0
    expired: int = 0
    errors: int = 0

    def as_dict(self) -> dict:
        return {
            "claimed": self.claimed,
            "applied": self.applied,
            "needs_attention": self.needs_attention,
            "expired": self.expired,
            "errors": self.errors,
        }


def _daily_cap_remaining(db: Session, cap: int) -> int:
    now = datetime.now(UTC)
    today_start = (
        datetime.combine(now.astimezone(IST).date(), datetime.min.time())
        .replace(tzinfo=IST)
        .astimezone(UTC)
    )
    already = len(
        db.scalars(
            select(Job.id).where(Job.status == JobStatus.APPLIED, Job.applied_at >= today_start)
        ).all()
    )
    return max(0, cap - already)


def _move(db: Session, job: Job, to: JobStatus, actor: Actor, note: str | None = None) -> None:
    t = check_transition(job.status, to, actor, note)
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


def _answer_lookup_factory(db: Session, embed):
    """Exact match against fixed/rule-based answers first (cheap, no model needed);
    otherwise semantic match via the embedding model, per docs/09_answer_bank.md."""
    thresholds = None

    def lookup(question: str) -> tuple[str | None, str | None, float | None]:
        nonlocal thresholds
        exact = db.scalar(select(Answer).where(Answer.canonical_question.ilike(question.strip())))
        if exact is not None:
            return exact.answer, str(exact.id), 1.0
        if thresholds is None:
            row = db.get(AppSettings, 1)
            thresholds = (row.data if row else DEFAULT_SETTINGS)["match_thresholds"]
        vector = embed([question])[0]
        m = match_question(db, vector, strong=thresholds["strong"], possible=thresholds["possible"])
        if m.tier == "strong":
            return m.answer, m.answer_id, m.score
        return None, None, None

    return lookup


def _apply_one(
    db: Session,
    job: Job,
    browser,
    applicant,
    storage,
    answer_lookup,
    dry_run: bool,
    counts: ApplyCounts,
) -> None:
    config = RUNNER_CONFIGS.get(job.company.platform.value)
    if config is None:
        _move(db, job, JobStatus.NEEDS_ATTENTION, Actor.APPLIER, "quick_apply")
        counts.needs_attention += 1
        db.commit()
        return

    page = browser.new_page()
    try:
        page.goto(job.url, timeout=30000, wait_until="domcontentloaded")
        blocked = detect_blocked(page)
        if blocked == "expired":
            _move(db, job, JobStatus.EXPIRED, Actor.APPLIER, "posting closed")
            counts.expired += 1
        elif blocked in {"captcha", "login"}:
            _screenshot(page, storage, job)
            _move(db, job, JobStatus.NEEDS_ATTENTION, Actor.APPLIER, blocked)
            counts.needs_attention += 1
        else:
            doc_path = job.document.resume_pdf_path if job.document else None
            with _local_resume_file(storage, doc_path) as resume_path:
                outcome = fill_form(
                    page,
                    config,
                    applicant=applicant,
                    resume_path=resume_path,
                    cover_letter=(job.document.cover_letter if job.document else "") or "",
                    answer_lookup=answer_lookup,
                )
            if outcome.unanswered:
                _move(
                    db,
                    job,
                    JobStatus.NEEDS_ATTENTION,
                    Actor.APPLIER,
                    f"question:{outcome.unanswered[0]}",
                )
                counts.needs_attention += 1
            elif dry_run:
                pass  # form filled, not submitted, job stays approved (test plan G11)
            else:
                submit_form(page, config, dry_run=False)
                if looks_submitted(page, config):
                    for label, value, answer_id, score in outcome.filled:
                        db.add(
                            ApplicationAnswer(
                                job_id=job.id,
                                question_text=label,
                                answer_submitted=value,
                                answer_id=answer_id,
                                match_score=score,
                            )
                        )
                    job.confirmation_path = _screenshot(page, storage, job)
                    _move(db, job, JobStatus.APPLIED, Actor.APPLIER)
                    job.applied_at = datetime.now(UTC)
                    counts.applied += 1
                else:
                    _screenshot(page, storage, job)
                    _move(
                        db, job, JobStatus.NEEDS_ATTENTION, Actor.APPLIER, "submit didn't confirm"
                    )
                    counts.needs_attention += 1
        db.commit()
    except Blocked as exc:
        _screenshot(page, storage, job)
        _move(db, job, JobStatus.NEEDS_ATTENTION, Actor.APPLIER, exc.reason)
        counts.needs_attention += 1
        db.commit()
    except Exception:
        log.exception("apply failed for job %s", job.id)
        db.rollback()
        counts.errors += 1
    finally:
        page.close()


@contextmanager
def _local_resume_file(storage, path: str | None):
    """Playwright's `set_input_files` needs a real local path. `LocalStorage` already
    has one; `SupabaseStorage` needs the bytes pulled down to a temp file first."""
    if not path:
        yield None
        return
    if hasattr(storage, "root"):
        yield str(storage.root / path)
        return
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        f.write(storage.get_bytes(path))
        tmp_path = f.name
    try:
        yield tmp_path
    finally:
        Path(tmp_path).unlink(missing_ok=True)


def _screenshot(page, storage, job: Job) -> str | None:
    try:
        png = page.screenshot(full_page=True)
    except Exception:
        return None
    path = f"confirmations/{job.id}.png"
    storage.put(path, png, "image/png")
    return path


def run_apply_once(
    db: Session,
    *,
    dry_run: bool = True,
    headless: bool = True,
    browser_factory=None,
    embed_fn=None,
) -> ApplyCounts:
    from workers.finder import start_run as take_run_lock

    settings = get_settings()
    run = take_run_lock(db, RunKind.APPLY, RunTrigger.MANUAL)
    if run is None:
        log.info("apply already running; skipping")
        return ApplyCounts()

    counts = ApplyCounts()
    try:
        row = db.get(AppSettings, 1)
        cfg = row.data if row else DEFAULT_SETTINGS
        cap = _daily_cap_remaining(db, cfg["daily_apply_cap"])
        if cap <= 0:
            run.status = RunStatus.OK
            return counts

        profile_row = db.scalar(select(ProfileVersion).order_by(ProfileVersion.version.desc()))
        profile = (
            Profile.from_dict(profile_row.facts, version=profile_row.version)
            if profile_row
            else Profile.load("profile/facts.yaml")
        )
        applicant = applicant_from_identity(profile.identity)
        storage = make_storage(settings)

        jobs = db.scalars(
            select(Job)
            .join(Company)
            .where(Job.status == JobStatus.APPROVED, Company.apply_mode == "auto")
            .options(selectinload(Job.company), selectinload(Job.document))
            .order_by(Job.fit_score.desc().nullslast())
            .limit(cap)
        ).all()
        if not jobs:
            run.status = RunStatus.OK
            return counts

        if browser_factory is None:
            from applier.browser import launch_browser

            browser_factory = lambda: launch_browser(headless=headless)  # noqa: E731
        if embed_fn is None:
            from app.llm.embeddings import LocalEmbeddingProvider

            embed_fn = LocalEmbeddingProvider().embed

        answer_lookup = _answer_lookup_factory(db, embed_fn)
        with browser_factory() as browser:
            for job in jobs:
                counts.claimed += 1
                _apply_one(db, job, browser, applicant, storage, answer_lookup, dry_run, counts)
        run.status = RunStatus.PARTIAL if counts.errors else RunStatus.OK
    except Exception as exc:
        db.rollback()
        run.status, run.error = RunStatus.FAILED, repr(exc)
        raise
    finally:
        run.counts = counts.as_dict()
        run.finished_at = datetime.now(UTC)
        db.merge(run)
        db.commit()
    return counts
