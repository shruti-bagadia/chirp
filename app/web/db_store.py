"""Database-backed dashboard store (M3). Same method surface as `demo_store.DemoStore`,
so `app/web/routes.py` doesn't need to know which one it's talking to.

Where `DemoStore` faked state in memory, this one reads and writes the real tables,
going through `app.services.states.check_transition` for every job status change (per
CLAUDE.md: "All job status changes go through states.check_transition and write a
JobEvent") and writing an audit `JobEvent` row every time.
"""

from __future__ import annotations

import hashlib
import logging
import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload, sessionmaker

from app.core.config import get_settings
from app.core.defaults import DEFAULT_SETTINGS
from app.db.enums import (
    Actor,
    CompanyState,
    JobStatus,
    Pinned,
    RunKind,
    RunStatus,
    RunTrigger,
)
from app.db.enums import Tier as TierEnum
from app.db.models import (
    Answer,
    ApplicationAnswer,
    AppSettings,
    Company,
    Job,
    JobEvent,
    Run,
)
from app.services import github_dispatch
from app.services.answers import save_answer
from app.services.companies import add_from_url
from app.services.ctc import validate_override
from app.services.schedule import DAYS, StepSchedule, format_ist, next_run, parse_time
from app.services.states import InvalidTransition, check_transition

log = logging.getLogger("chirp.web.store")

QUESTION_PREFIX = "question:"

# Which finished run (by id) has already produced a toast, per kind. Module-level
# because `DbStore` is constructed fresh per request; this just avoids repeating the
# same "Found 3 new jobs" toast on every `/runs/strip` poll after a run finishes.
_last_reported: dict[str, str] = {}

PLATFORM_LABELS = {
    "greenhouse": "Greenhouse",
    "lever": "Lever",
    "ashby": "Ashby",
    "workday": "Workday",
    "successfactors": "SuccessFactors",
    "darwinbox": "Darwinbox",
    "oracle": "Oracle",
    "icims": "iCIMS",
    "smartrecruiters": "SmartRecruiters",
    "own": "Company site",
    "unknown": "Unknown",
}


def utcnow() -> datetime:
    return datetime.now(UTC)


def question_hand_id(question: str) -> str:
    return "q_" + hashlib.sha1(question.strip().encode("utf-8")).hexdigest()[:12]


# ----- View objects: same attribute surface the templates already expect -----


@dataclass
class JobView:
    id: str
    score: int
    title: str
    company: str
    location: str
    mode: str
    ctc: float
    why: str
    matches: list[str]
    gaps: list[str]
    changes: str
    status: str
    cover_letter: str = ""


@dataclass
class HandView:
    id: str
    kind: str  # question | quick | blocked
    question: str = ""
    companies: list[str] = field(default_factory=list)
    company: str = ""
    role: str = ""
    platform: str = ""
    reason: str = ""
    # quick-apply only:
    job_id: str = ""
    resume_pdf_path: str | None = None
    cover_letter: str = ""
    expected_ctc: str = ""
    notice_period: str = "15 days"
    location: str = "Pune"
    why_company: str = ""


@dataclass
class FlownView:
    id: str
    company: str
    role: str
    day: str
    callback: bool
    url: str
    expected_ctc: str
    via: str
    cover_letter: str
    answers: list[tuple[str, str]]


@dataclass
class AnswerView:
    id: str
    question: str
    answer: str
    short_answer: str
    type: str
    category: str
    times_used: int


@dataclass
class CompanyView:
    id: str
    name: str
    tier: str
    state: str
    platform: str
    apply_mode: str
    pinned: str
    priority_score: int
    careers_url: str


def _job_view(job: Job) -> JobView:
    doc = job.document
    return JobView(
        id=str(job.id),
        score=job.fit_score or 0,
        title=job.title,
        company=job.company.name,
        location=job.location,
        mode=(job.work_mode.value if job.work_mode else "unknown").title(),
        ctc=float(job.expected_ctc_lpa) if job.expected_ctc_lpa is not None else 0.0,
        why=job.fit_summary or "",
        matches=list(job.fit_matches or []),
        gaps=list(job.fit_gaps or []),
        changes=(doc.change_summary if doc else "") or "",
        status=job.status.value,
        cover_letter=(doc.cover_letter if doc else "") or "",
    )


def _day_label(dt: datetime | None, now: datetime) -> str:
    if dt is None:
        return ""
    days = (now.date() - dt.date()).days
    if days <= 0:
        return "Today"
    if days == 1:
        return "Yesterday"
    return dt.strftime("%a")


class DbStore:
    def __init__(self, db: Session) -> None:
        self.db = db
        self._settings_row: AppSettings | None = None

    # ----- Settings (single row) -----

    def _settings(self) -> AppSettings:
        if self._settings_row is None:
            row = self.db.get(AppSettings, 1)
            if row is None:
                row = AppSettings(id=1, data=dict(DEFAULT_SETTINGS))
                self.db.add(row)
                self.db.commit()
            self._settings_row = row
        return self._settings_row

    @property
    def settings(self) -> dict:
        return self._settings().data

    def _save_settings(self, data: dict) -> None:
        row = self._settings()
        row.data = data  # reassign (not mutate) so SQLAlchemy sees the JSONB change
        self.db.add(row)
        self.db.commit()

    @property
    def schedule(self) -> dict:
        return self.settings["schedule"]

    # ----- Nest -----

    def _job_query(self, status: JobStatus):
        return (
            select(Job)
            .join(Company)
            .where(Job.status == status)
            .options(selectinload(Job.company), selectinload(Job.document))
        )

    def pending(self) -> list[JobView]:
        rows = self.db.scalars(
            self._job_query(JobStatus.PENDING_REVIEW).order_by(Job.fit_score.desc())
        ).all()
        return [_job_view(j) for j in rows]

    def approved(self) -> list[JobView]:
        rows = self.db.scalars(self._job_query(JobStatus.APPROVED)).all()
        return [_job_view(j) for j in rows]

    def _get_job_row(self, job_id: str) -> Job | None:
        try:
            return self.db.scalar(
                select(Job)
                .where(Job.id == job_id)
                .options(selectinload(Job.company), selectinload(Job.document))
            )
        except Exception:  # malformed UUID string
            return None

    def get_job(self, job_id: str) -> JobView | None:
        job = self._get_job_row(job_id)
        return _job_view(job) if job else None

    def decide(self, ids: list[str], action: str) -> int:
        if action not in {"approve", "reject"}:
            raise ValueError("Action must be approve or reject.")
        target = JobStatus.APPROVED if action == "approve" else JobStatus.REJECTED
        n = 0
        for job_id in ids:
            job = self._get_job_row(str(job_id))
            if job is None or job.status != JobStatus.PENDING_REVIEW:
                continue  # already changed elsewhere, or gone: skip, don't error (E11)
            try:
                t = check_transition(job.status, target, Actor.YOU)
            except InvalidTransition:
                continue
            job.status = t.to_status
            self.db.add(
                JobEvent(
                    job_id=job.id, from_status=t.from_status, to_status=t.to_status, actor=t.actor
                )
            )
            n += 1
        self.db.commit()
        return n

    def set_ctc(self, job_id: str, value: float) -> JobView:
        job = self._get_job_row(job_id)
        if job is None:
            raise KeyError(job_id)
        job.expected_ctc_lpa = validate_override(value)
        job.ctc_overridden = True
        self.db.commit()
        return _job_view(job)

    # ----- Hands (needs_attention jobs, grouped) -----

    def _needs_attention_jobs(self) -> list[Job]:
        return list(self.db.scalars(self._job_query(JobStatus.NEEDS_ATTENTION)).all())

    @property
    def hands(self) -> list[HandView]:
        return self._all_hands()

    def _all_hands(self) -> list[HandView]:
        jobs = self._needs_attention_jobs()
        questions: dict[str, HandView] = {}
        out: list[HandView] = []
        s = self.settings
        band = s["ctc_tiers"]
        for job in jobs:
            reason = job.status_reason or ""
            if reason.startswith(QUESTION_PREFIX):
                text = reason[len(QUESTION_PREFIX) :]
                hid = question_hand_id(text)
                if hid not in questions:
                    questions[hid] = HandView(id=hid, kind="question", question=text, companies=[])
                    out.append(questions[hid])
                questions[hid].companies.append(job.company.name)
            elif reason == "quick_apply":
                doc = job.document
                ctc = f"{job.expected_ctc_lpa:g} LPA" if job.expected_ctc_lpa else "—"
                tier_band = band.get(job.company.tier.value, {})
                out.append(
                    HandView(
                        id=str(job.id),
                        kind="quick",
                        company=job.company.name,
                        role=job.title,
                        platform=PLATFORM_LABELS.get(job.company.platform.value, "Unknown"),
                        job_id=str(job.id),
                        resume_pdf_path=doc.resume_pdf_path if doc else None,
                        cover_letter=(doc.cover_letter if doc else "") or "",
                        expected_ctc=ctc
                        or (
                            f"{tier_band.get('min', '')}–{tier_band.get('max', '')} LPA"
                            if tier_band
                            else ""
                        ),
                        why_company=(
                            f"{job.company.name}'s engineering work lines up with what I build."
                        ),
                    )
                )
            else:
                out.append(
                    HandView(
                        id=str(job.id),
                        kind="blocked",
                        company=job.company.name,
                        role=job.title,
                        reason=reason or "unknown",
                    )
                )
        return out

    def get_hand(self, hand_id: str) -> HandView | None:
        return next((h for h in self._all_hands() if h.id == hand_id), None)

    def answer(self, hand_id: str, text: str, save_to_bank: bool = True) -> HandView:
        if not text.strip():
            raise ValueError("Write an answer first.")
        hand = self.get_hand(hand_id)
        if hand is None or hand.kind != "question":
            raise KeyError(hand_id)
        if save_to_bank:
            save_answer(self.db, hand.question, text)
        jobs = self._needs_attention_jobs()
        for job in jobs:
            reason = job.status_reason or ""
            if (
                reason.startswith(QUESTION_PREFIX)
                and question_hand_id(reason[len(QUESTION_PREFIX) :]) == hand_id
            ):
                t = check_transition(job.status, JobStatus.APPROVED, Actor.YOU, note="answered")
                job.status, job.status_reason = t.to_status, None
                self.db.add(
                    JobEvent(
                        job_id=job.id,
                        from_status=t.from_status,
                        to_status=t.to_status,
                        actor=t.actor,
                        note=t.note,
                    )
                )
        self.db.commit()
        return hand

    def _transition_hand_job(
        self, hand_id: str, to: JobStatus, note: str | None = None
    ) -> HandView:
        hand = self.get_hand(hand_id)
        if hand is None:
            raise KeyError(hand_id)
        job = self._get_job_row(hand_id)
        if job is None:
            raise KeyError(hand_id)
        t = check_transition(job.status, to, Actor.YOU, note)
        job.status, job.status_reason = t.to_status, None
        if to == JobStatus.APPLIED:
            job.applied_at = utcnow()
        self.db.add(
            JobEvent(
                job_id=job.id,
                from_status=t.from_status,
                to_status=t.to_status,
                actor=t.actor,
                note=t.note,
            )
        )
        self.db.commit()
        return hand

    def mark_applied(self, hand_id: str) -> HandView:
        return self._transition_hand_job(hand_id, JobStatus.APPLIED, "quick apply, marked by you")

    def retry(self, hand_id: str) -> HandView:
        return self._transition_hand_job(hand_id, JobStatus.APPROVED, "retry")

    # ----- Flown -----

    def _flown_query(self):
        return (
            select(Job)
            .join(Company)
            .where(Job.status == JobStatus.APPLIED)
            .options(selectinload(Job.company), selectinload(Job.document))
            .order_by(Job.applied_at.desc().nullslast())
        )

    def _flown_view(self, job: Job, now: datetime) -> FlownView:
        doc = job.document
        via = "You"
        last_event = self.db.scalar(
            select(JobEvent)
            .where(JobEvent.job_id == job.id, JobEvent.to_status == JobStatus.APPLIED)
            .order_by(JobEvent.created_at.desc())
        )
        if last_event is not None and last_event.actor == Actor.APPLIER:
            via = "Chirp"
        answers = self.db.scalars(
            select(ApplicationAnswer)
            .where(ApplicationAnswer.job_id == job.id)
            .order_by(ApplicationAnswer.created_at)
        ).all()
        return FlownView(
            id=str(job.id),
            company=job.company.name,
            role=job.title,
            day=_day_label(job.applied_at, now),
            callback=bool(job.got_callback),
            url=job.url,
            expected_ctc=f"{job.expected_ctc_lpa:g} LPA" if job.expected_ctc_lpa else "—",
            via=via,
            cover_letter=(doc.cover_letter if doc else "") or "",
            answers=[(a.question_text, a.answer_submitted) for a in answers],
        )

    @property
    def flown(self) -> list[FlownView]:
        now = utcnow()
        rows = self.db.scalars(self._flown_query()).all()
        return [self._flown_view(j, now) for j in rows]

    def get_flown(self, flown_id: str) -> FlownView | None:
        job = self._get_job_row(flown_id)
        if job is None or job.status != JobStatus.APPLIED:
            return None
        return self._flown_view(job, utcnow())

    def toggle_callback(self, flown_id: str) -> FlownView:
        job = self._get_job_row(flown_id)
        if job is None or job.status != JobStatus.APPLIED:
            raise KeyError(flown_id)
        job.got_callback = not bool(job.got_callback)
        self.db.commit()
        return self._flown_view(job, utcnow())

    # ----- Schedule and limits -----

    def add_time(self, step: str, value: str) -> None:
        data = self.settings
        t = parse_time(value).strftime("%H:%M")
        times = data["schedule"][step]["times"]
        if t not in times:
            times.append(t)
            times.sort()
        self._save_settings(data)

    def remove_time(self, step: str, value: str) -> None:
        data = self.settings
        data["schedule"][step]["times"] = [t for t in data["schedule"][step]["times"] if t != value]
        self._save_settings(data)

    def toggle_day(self, day: str) -> None:
        if day not in DAYS:
            raise ValueError(f"Unknown day: {day}")
        data = self.settings
        for step in ("find", "apply"):
            days = data["schedule"][step]["days"]
            if day in days:
                days.remove(day)
            else:
                days.append(day)
                days.sort(key=DAYS.index)
        self._save_settings(data)

    def toggle_pause(self) -> bool:
        data = self.settings
        data["schedule"]["paused"] = not data["schedule"]["paused"]
        self._save_settings(data)
        return data["schedule"]["paused"]

    def step_limit(self, name: str, delta: int) -> int:
        bounds = {"daily_apply_cap": (1, 20), "fit_threshold": (50, 95)}
        if name not in bounds:
            raise ValueError(f"Unknown limit: {name}")
        low, high = bounds[name]
        data = self.settings
        data[name] = max(low, min(high, data[name] + delta))
        self._save_settings(data)
        return data[name]

    # ----- Runs -----

    def is_running(self, kind: str, now: datetime) -> bool:
        return (
            self.db.scalar(
                select(Run.id).where(Run.kind == RunKind(kind), Run.status == RunStatus.RUNNING)
            )
            is not None
        )

    def start_run(self, kind: str, now: datetime) -> bool:
        """Kick off a real Find/Process run (or an Apply run request) in the background.

        Returns False immediately if a run of this kind is already going (the run lock
        in the `runs` table itself is authoritative; this is just an up-front check so
        the button click gets an instant "already running" instead of always trying).
        """
        if self.is_running(kind, now):
            return False
        if kind == "find":
            settings = get_settings()
            if github_dispatch.is_configured(settings):
                # Deployed setup (dashboard on Render, Finder on GitHub Actions per
                # docs/03_architecture.md): dispatch the real workflow instead of
                # running the scrape + LLM calls + PDF compiles on the web dyno.
                try:
                    github_dispatch.dispatch_find(settings)
                    return True
                except github_dispatch.DispatchError:
                    log.exception("GitHub dispatch failed; falling back to a local run")
        # Bind the background thread's own session to the SAME engine this request's
        # session uses (not the globally-cached `get_sessionmaker()`), so tests that
        # override `get_db` with a test database don't have a background thread
        # quietly go off and hit the real dev database (and real company APIs).
        sessionmaker_ = sessionmaker(bind=self.db.get_bind(), expire_on_commit=False)
        if kind == "find":
            threading.Thread(
                target=_run_find_and_process, args=(sessionmaker_,), daemon=True
            ).start()
        elif kind == "apply":
            threading.Thread(target=_run_apply, args=(sessionmaker_,), daemon=True).start()
        return True

    def finish_runs(self, now: datetime) -> list[tuple[str, str]]:
        """(kind, toast message) for runs that finished since we last looked."""
        out: list[tuple[str, str]] = []
        for kind in (RunKind.FIND, RunKind.APPLY):
            last = self.db.scalar(
                select(Run).where(Run.kind == kind).order_by(Run.started_at.desc()).limit(1)
            )
            if last is None or last.status == RunStatus.RUNNING:
                continue
            if _last_reported.get(kind.value) == str(last.id):
                continue
            _last_reported[kind.value] = str(last.id)
            counts = last.counts or {}
            if kind == RunKind.FIND:
                kept = counts.get("kept", 0)
                msg = (
                    f"Found {kept} new job{'s' if kept != 1 else ''}."
                    if kept
                    else "Nest is up to date."
                )
            else:
                applied = counts.get("applied", 0)
                msg = f"Flew {applied} application{'s' if applied != 1 else ''}."
            out.append((kind.value, msg))
        return out

    def next_label(self, step: str, now: datetime) -> str:
        s = StepSchedule.from_dict(self.schedule[step])
        nxt = next_run(s, now, paused=self.schedule["paused"])
        return format_ist(nxt, now) if nxt else "not scheduled"

    # ----- Answers -----

    def answers(self, category: str | None = None) -> list[AnswerView]:
        q = select(Answer).order_by(Answer.category, Answer.canonical_question)
        if category:
            q = q.where(Answer.category == category)
        return [
            AnswerView(
                id=str(a.id),
                question=a.canonical_question,
                answer=a.answer,
                short_answer=a.short_answer or "",
                type=a.type.value,
                category=a.category.value,
                times_used=a.times_used,
            )
            for a in self.db.scalars(q).all()
        ]

    def get_answer(self, answer_id: str) -> AnswerView | None:
        return next((a for a in self.answers() if a.id == answer_id), None)

    def update_answer(self, answer_id: str, answer_text: str, short_answer: str = "") -> AnswerView:
        row = self.db.get(Answer, answer_id)
        if row is None:
            raise KeyError(answer_id)
        if not answer_text.strip():
            raise ValueError("Write an answer first.")
        row.answer = answer_text.strip()
        row.short_answer = short_answer.strip() or None
        row.version += 1
        self.db.commit()
        return self.get_answer(answer_id)

    # ----- Companies -----

    def _company_view(self, c: Company) -> CompanyView:
        return CompanyView(
            id=str(c.id),
            name=c.name,
            tier=c.tier.value,
            state=c.state.value,
            platform=PLATFORM_LABELS.get(c.platform.value, c.platform.value),
            apply_mode=c.apply_mode.value,
            pinned=c.pinned.value,
            priority_score=c.priority_score,
            careers_url=c.careers_url or "",
        )

    def candidate_companies(self) -> list[CompanyView]:
        rows = self.db.scalars(
            select(Company).where(Company.state == CompanyState.CANDIDATE).order_by(Company.name)
        ).all()
        return [self._company_view(c) for c in rows]

    def active_companies(self) -> list[CompanyView]:
        rank = {Pinned.HIGH: 0, Pinned.NONE: 1, Pinned.LOW: 2}
        rows = self.db.scalars(select(Company).where(Company.state == CompanyState.ACTIVE)).all()
        rows.sort(key=lambda c: (rank[c.pinned], -c.priority_score, c.name))
        return [self._company_view(c) for c in rows]

    def get_company(self, company_id: str) -> CompanyView | None:
        c = self.db.get(Company, company_id)
        return self._company_view(c) if c else None

    def approve_candidate(self, company_id: str, tier: str) -> CompanyView:
        c = self.db.get(Company, company_id)
        if c is None:
            raise KeyError(company_id)
        c.state = CompanyState.ACTIVE
        c.tier = TierEnum(tier)
        self.db.commit()
        return self._company_view(c)

    def block_company(self, company_id: str) -> CompanyView:
        c = self.db.get(Company, company_id)
        if c is None:
            raise KeyError(company_id)
        c.state = CompanyState.BLOCKED
        self.db.commit()
        return self._company_view(c)

    def set_company_pin(self, company_id: str, pinned: str) -> CompanyView:
        c = self.db.get(Company, company_id)
        if c is None:
            raise KeyError(company_id)
        c.pinned = Pinned(pinned)
        self.db.commit()
        return self._company_view(c)

    def set_company_tier(self, company_id: str, tier: str) -> CompanyView:
        c = self.db.get(Company, company_id)
        if c is None:
            raise KeyError(company_id)
        c.tier = TierEnum(tier)
        self.db.commit()
        return self._company_view(c)

    def add_company(self, url: str, tier: str) -> CompanyView:
        c = add_from_url(self.db, url, tier=TierEnum(tier))
        return self._company_view(c)

    # ----- Counts -----

    def counts(self) -> dict:
        return {
            "nest": len(self.pending()),
            "hands": len(self.hands),
            "ready": len(self.approved()),
        }


def _run_find_and_process(sessionmaker_) -> None:
    from app.connectors.http import HttpFetcher
    from workers.finder import run_find
    from workers.processor import run_process

    with sessionmaker_() as db:
        fetcher = HttpFetcher()
        try:
            run = run_find(db, fetcher, trigger=RunTrigger.MANUAL)
        finally:
            fetcher.close()
        if run is not None:
            try:
                run_process(db, trigger=RunTrigger.MANUAL)
            except Exception:
                log.exception("process run failed after manual find")


def _run_apply(sessionmaker_) -> None:
    try:
        from applier.runner import run_apply_once
    except ImportError:
        log.warning("Fly now pressed, but the Applier isn't installed yet.")
        return
    with sessionmaker_() as db:
        try:
            run_apply_once(db, dry_run=get_settings().apply_dry_run)
        except Exception:
            log.exception("apply run failed")


def get_store(db: Session) -> DbStore:
    return DbStore(db)
