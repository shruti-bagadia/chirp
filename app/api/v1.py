"""Machine API for the Applier and the `chirp` CLI. Bearer-token auth (`CHIRP_API_TOKEN`).

See docs/05_api_design.md for the contract. Workers on GitHub Actions talk to the
database directly and don't use this; this surface exists for the laptop Applier,
which only has HTTPS, not a DB connection.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.config import get_settings
from app.core.security import tokens_match
from app.db.enums import Actor, JobStatus, RequestStatus, RunKind
from app.db.models import (
    Answer,
    ApplicationAnswer,
    Company,
    Job,
    JobEvent,
    ProfileVersion,
    RunRequest,
)
from app.db.session import get_db
from app.services.answers import match_question
from app.services.schedule import IST
from app.services.states import InvalidTransition, check_transition
from app.storage import make_storage

router = APIRouter(prefix="/api/v1", tags=["machine"])

LEASE_MINUTES = 15


def require_token(request: Request) -> None:
    settings = get_settings()
    given = request.headers.get("authorization", "")
    given = given[7:] if given.lower().startswith("bearer ") else ""
    if not tokens_match(given, settings.chirp_api_token.get_secret_value()):
        raise HTTPException(401, "Missing or invalid bearer token")


def err(code: str, message: str, status: int = 400) -> HTTPException:
    return HTTPException(status, {"error": {"code": code, "message": message}})


# ---------- Apply queue ----------


class ClaimRequest(BaseModel):
    max: int = Field(default=8, ge=1, le=50)


class ClaimedJob(BaseModel):
    id: str
    company: str
    title: str
    url: str
    platform: str
    apply_mode: str
    expected_ctc_lpa: float | None
    resume_pdf_url: str | None
    cover_letter: str
    lease_until: str


class ClaimResponse(BaseModel):
    remaining_cap_today: int
    jobs: list[ClaimedJob]


@router.post("/apply-queue/claim", dependencies=[Depends(require_token)])
def claim(body: ClaimRequest, db: Session = Depends(get_db)) -> ClaimResponse:
    from app.core.defaults import DEFAULT_SETTINGS
    from app.db.models import AppSettings

    now = datetime.now(UTC)
    row = db.get(AppSettings, 1)
    cap = (row.data if row else DEFAULT_SETTINGS)["daily_apply_cap"]
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
    remaining = max(0, cap - already)
    take = min(body.max, remaining)
    if take <= 0:
        return ClaimResponse(remaining_cap_today=0, jobs=[])

    storage = make_storage(get_settings())
    jobs = db.scalars(
        select(Job)
        .join(Company)
        .where(Job.status == JobStatus.APPROVED, Company.apply_mode == "auto")
        .options(selectinload(Job.company), selectinload(Job.document))
        .order_by(Job.fit_score.desc().nullslast())
        .limit(take)
    ).all()
    out = []
    lease_until = now + timedelta(minutes=LEASE_MINUTES)
    for job in jobs:
        t = check_transition(job.status, JobStatus.APPLYING, Actor.APPLIER)
        job.status, job.lease_until = t.to_status, lease_until
        db.add(
            JobEvent(job_id=job.id, from_status=t.from_status, to_status=t.to_status, actor=t.actor)
        )
        resume_url = None
        if job.document and job.document.resume_pdf_path:
            resume_url = storage.signed_url(job.document.resume_pdf_path)
        out.append(
            ClaimedJob(
                id=str(job.id),
                company=job.company.name,
                title=job.title,
                url=job.url,
                platform=job.company.platform.value,
                apply_mode=job.company.apply_mode.value,
                expected_ctc_lpa=float(job.expected_ctc_lpa) if job.expected_ctc_lpa else None,
                resume_pdf_url=resume_url,
                cover_letter=(job.document.cover_letter if job.document else "") or "",
                lease_until=lease_until.isoformat(),
            )
        )
    db.commit()
    return ClaimResponse(remaining_cap_today=remaining - len(out), jobs=out)


def _leased_job(db: Session, job_id: str) -> Job:
    job = db.scalar(select(Job).where(Job.id == job_id))
    if job is None:
        raise err("not_found", "No such job", 404)
    if job.status != JobStatus.APPLYING or job.lease_until is None:
        raise err("lease_expired", "This job isn't leased to you", 409)
    if job.lease_until < datetime.now(UTC):
        raise err("lease_expired", "Your lease on this job expired", 409)
    return job


@router.post("/jobs/{job_id}/heartbeat", dependencies=[Depends(require_token)])
def heartbeat(job_id: str, db: Session = Depends(get_db)) -> dict:
    job = _leased_job(db, job_id)
    job.lease_until = datetime.now(UTC) + timedelta(minutes=LEASE_MINUTES)
    db.commit()
    return {"lease_until": job.lease_until.isoformat()}


class AnswerSubmitted(BaseModel):
    question_text: str
    answer: str
    answer_id: str | None = None
    match_score: float | None = None


class ResultRequest(BaseModel):
    outcome: str  # applied | needs_attention | expired
    reason: str | None = None
    unanswered_questions: list[str] = Field(default_factory=list)
    answers_submitted: list[AnswerSubmitted] = Field(default_factory=list)
    confirmation_screenshot: str | None = None  # base64


@router.post("/jobs/{job_id}/result", dependencies=[Depends(require_token)])
def result(job_id: str, body: ResultRequest, db: Session = Depends(get_db)) -> dict:
    job = _leased_job(db, job_id)
    target = {
        "applied": JobStatus.APPLIED,
        "needs_attention": JobStatus.NEEDS_ATTENTION,
        "expired": JobStatus.EXPIRED,
    }.get(body.outcome)
    if target is None:
        raise err("bad_outcome", f"Unknown outcome: {body.outcome}")

    note = body.reason
    if target == JobStatus.NEEDS_ATTENTION and body.unanswered_questions:
        note = f"question:{body.unanswered_questions[0]}"
    try:
        t = check_transition(job.status, target, Actor.APPLIER, note)
    except InvalidTransition as exc:
        raise err("invalid_transition", str(exc), 409) from exc
    job.status, job.status_reason, job.lease_until = t.to_status, t.note, None
    if target == JobStatus.APPLIED:
        job.applied_at = datetime.now(UTC)
        if body.confirmation_screenshot:
            path = f"confirmations/{job.id}.png"
            import base64

            make_storage(get_settings()).put(
                path, base64.b64decode(body.confirmation_screenshot), "image/png"
            )
            job.confirmation_path = path
    db.add(
        JobEvent(
            job_id=job.id,
            from_status=t.from_status,
            to_status=t.to_status,
            actor=t.actor,
            note=t.note,
        )
    )
    for a in body.answers_submitted:
        db.add(
            ApplicationAnswer(
                job_id=job.id,
                question_text=a.question_text,
                answer_submitted=a.answer,
                answer_id=a.answer_id,
                match_score=a.match_score,
            )
        )
    db.commit()
    return {"status": "ok"}


# ---------- Profile (PII is fine here; never sent to an LLM) ----------


@router.get("/profile", dependencies=[Depends(require_token)])
def profile(db: Session = Depends(get_db)) -> dict:
    from app.profile.model import Profile

    row = db.scalar(select(ProfileVersion).order_by(ProfileVersion.version.desc()))
    if row is not None:
        p = Profile.from_dict(row.facts, version=row.version)
    else:
        p = Profile.load(Path("profile/facts.yaml"))
    fixed = {
        a.canonical_question: a.answer
        for a in db.scalars(select(Answer)).all()
        if a.type.value in {"fixed", "rule_based"}
    }
    return {"identity": p.identity, "fixed_answers": fixed}


class ProfilePush(BaseModel):
    facts: dict
    note: str = ""


@router.post("/profile", dependencies=[Depends(require_token)])
def profile_push(body: ProfilePush, db: Session = Depends(get_db)) -> dict:
    from app.profile.model import Profile

    Profile.from_dict(body.facts)  # validates before saving
    next_version = (
        db.scalar(select(ProfileVersion.version).order_by(ProfileVersion.version.desc())) or 0
    ) + 1
    row = ProfileVersion(version=next_version, facts=body.facts, note=body.note)
    db.add(row)
    db.commit()
    return {"version": next_version}


# ---------- Answer matching ----------


class MatchRequest(BaseModel):
    question_text: str
    embedding: list[float]


@router.post("/answers/match", dependencies=[Depends(require_token)])
def answers_match(body: MatchRequest, db: Session = Depends(get_db)) -> dict:
    from app.core.defaults import DEFAULT_SETTINGS
    from app.db.models import AppSettings

    row = db.get(AppSettings, 1)
    thresholds = (row.data if row else DEFAULT_SETTINGS)["match_thresholds"]
    m = match_question(
        db, body.embedding, strong=thresholds["strong"], possible=thresholds["possible"]
    )
    return {
        "match": m.tier,
        "score": m.score,
        "answer_id": m.answer_id,
        "answer": m.answer,
        "short_answer": m.short_answer,
    }


# ---------- Applier check-in ----------


class CheckinRequest(BaseModel):
    version: str
    busy: bool = False


@router.post("/applier/checkin", dependencies=[Depends(require_token)])
def checkin(body: CheckinRequest, db: Session = Depends(get_db)) -> dict:
    from app.db.models import ApplierHeartbeat

    now = datetime.now(UTC)
    row = db.get(ApplierHeartbeat, 1)
    if row is None:
        row = ApplierHeartbeat(id=1, last_seen_at=now, version=body.version, busy=body.busy)
        db.add(row)
    else:
        row.last_seen_at, row.version, row.busy = now, body.version, body.busy

    request_row = None
    if not body.busy:
        request_row = db.scalar(
            select(RunRequest)
            .where(RunRequest.kind == RunKind.APPLY, RunRequest.status == RequestStatus.WAITING)
            .order_by(RunRequest.created_at)
        )
        if request_row is not None:
            request_row.status, request_row.picked_up_at = RequestStatus.PICKED_UP, now
    db.commit()
    if request_row is not None:
        return {
            "start": True,
            "reason": request_row.source.value,
            "request_id": str(request_row.id),
        }
    return {"start": False, "reason": None, "request_id": None}
