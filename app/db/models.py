"""All Chirp tables. See docs/04_data_model.md."""

from __future__ import annotations

import uuid
from datetime import date, datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    ARRAY,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, IdMixin, TimestampMixin, pg_enum
from app.db.enums import (
    Actor,
    AnswerCategory,
    AnswerType,
    ApplyMode,
    CompanyCategory,
    CompanySource,
    CompanyState,
    JobStatus,
    Pinned,
    Platform,
    RequestSource,
    RequestStatus,
    RunKind,
    RunStatus,
    RunTrigger,
    Tier,
    WorkMode,
)

EMBEDDING_DIM = 384  # all-MiniLM-L6-v2; change with a migration if the model changes


class Company(IdMixin, TimestampMixin, Base):
    __tablename__ = "companies"

    name: Mapped[str] = mapped_column(String(200), unique=True)
    aliases: Mapped[list[str]] = mapped_column(ARRAY(String), server_default="{}")
    careers_url: Mapped[str | None] = mapped_column(Text)
    platform: Mapped[Platform] = mapped_column(
        pg_enum(Platform, "platform"), default=Platform.UNKNOWN
    )
    platform_board_id: Mapped[str | None] = mapped_column(String(200))
    apply_mode: Mapped[ApplyMode] = mapped_column(
        pg_enum(ApplyMode, "apply_mode"), default=ApplyMode.QUICK_APPLY
    )
    category: Mapped[CompanyCategory | None] = mapped_column(
        pg_enum(CompanyCategory, "company_category")
    )
    tier: Mapped[Tier] = mapped_column(pg_enum(Tier, "tier"), default=Tier.STANDARD)
    state: Mapped[CompanyState] = mapped_column(
        pg_enum(CompanyState, "company_state"), default=CompanyState.CANDIDATE
    )
    priority_score: Mapped[int] = mapped_column(Integer, default=50)
    pinned: Mapped[Pinned] = mapped_column(pg_enum(Pinned, "pinned"), default=Pinned.NONE)
    source: Mapped[CompanySource] = mapped_column(
        pg_enum(CompanySource, "company_source"), default=CompanySource.SEED
    )
    last_match_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0)

    jobs: Mapped[list[Job]] = relationship(back_populates="company")


class Job(IdMixin, TimestampMixin, Base):
    __tablename__ = "jobs"
    __table_args__ = (
        Index("ix_jobs_status_score", "status", text("fit_score DESC")),
        Index("ix_jobs_company_status", "company_id", "status"),
        Index("ix_jobs_lease_until", "lease_until"),
    )

    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id"))
    external_id: Mapped[str | None] = mapped_column(String(200))
    url: Mapped[str] = mapped_column(Text)
    canonical_url: Mapped[str] = mapped_column(Text, unique=True)
    dedupe_key: Mapped[str] = mapped_column(String(64), unique=True)
    title: Mapped[str] = mapped_column(String(300))
    location: Mapped[str] = mapped_column(String(300), default="")
    work_mode: Mapped[WorkMode] = mapped_column(
        pg_enum(WorkMode, "work_mode"), default=WorkMode.UNKNOWN
    )
    description: Mapped[str] = mapped_column(Text, default="")
    salary_min_lpa: Mapped[float | None] = mapped_column(Numeric(6, 2))
    salary_max_lpa: Mapped[float | None] = mapped_column(Numeric(6, 2))
    experience_min: Mapped[float | None] = mapped_column(Numeric(4, 1))
    experience_max: Mapped[float | None] = mapped_column(Numeric(4, 1))
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    status: Mapped[JobStatus] = mapped_column(
        pg_enum(JobStatus, "job_status"), default=JobStatus.DISCOVERED
    )
    status_reason: Mapped[str | None] = mapped_column(Text)
    fit_score: Mapped[int | None] = mapped_column(Integer)
    fit_summary: Mapped[str | None] = mapped_column(Text)
    fit_gaps: Mapped[list[str]] = mapped_column(ARRAY(String), server_default="{}")
    fit_matches: Mapped[list[str]] = mapped_column(ARRAY(String), server_default="{}")
    role_focus: Mapped[str | None] = mapped_column(Text)
    flags: Mapped[list[str]] = mapped_column(ARRAY(String), server_default="{}")
    expected_ctc_lpa: Mapped[float | None] = mapped_column(Numeric(5, 1))
    ctc_overridden: Mapped[bool] = mapped_column(Boolean, default=False)
    batch: Mapped[str | None] = mapped_column(String(40))
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    confirmation_path: Mapped[str | None] = mapped_column(Text)
    got_callback: Mapped[bool | None] = mapped_column(Boolean)

    company: Mapped[Company] = relationship(back_populates="jobs")
    events: Mapped[list[JobEvent]] = relationship(
        back_populates="job", order_by="JobEvent.created_at"
    )
    document: Mapped[TailoredDocument | None] = relationship(back_populates="job", uselist=False)


class JobEvent(IdMixin, Base):
    """Append-only audit of every status change."""

    __tablename__ = "job_events"

    job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("jobs.id"), index=True)
    from_status: Mapped[JobStatus | None] = mapped_column(pg_enum(JobStatus, "job_status"))
    to_status: Mapped[JobStatus] = mapped_column(pg_enum(JobStatus, "job_status"))
    actor: Mapped[Actor] = mapped_column(pg_enum(Actor, "actor"))
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    job: Mapped[Job] = relationship(back_populates="events")


class TailoredDocument(IdMixin, TimestampMixin, Base):
    __tablename__ = "tailored_documents"

    job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("jobs.id"), unique=True)
    resume_pdf_path: Mapped[str | None] = mapped_column(Text)
    resume_tex: Mapped[str | None] = mapped_column(Text)
    selection: Mapped[dict] = mapped_column(JSONB, default=dict)
    change_summary: Mapped[str | None] = mapped_column(Text)
    cover_letter: Mapped[str | None] = mapped_column(Text)
    fabrication_check: Mapped[dict] = mapped_column(JSONB, default=dict)
    profile_version: Mapped[int | None] = mapped_column(Integer)
    prompt_version: Mapped[str | None] = mapped_column(String(40))

    job: Mapped[Job] = relationship(back_populates="document")


class Answer(IdMixin, TimestampMixin, Base):
    __tablename__ = "answers"

    canonical_question: Mapped[str] = mapped_column(Text)
    answer: Mapped[str] = mapped_column(Text)
    short_answer: Mapped[str | None] = mapped_column(String(300))
    type: Mapped[AnswerType] = mapped_column(pg_enum(AnswerType, "answer_type"))
    category: Mapped[AnswerCategory] = mapped_column(pg_enum(AnswerCategory, "answer_category"))
    times_used: Mapped[int] = mapped_column(Integer, default=0)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = mapped_column(Integer, default=1)

    variants: Mapped[list[QuestionVariant]] = relationship(back_populates="answer")


class QuestionVariant(IdMixin, TimestampMixin, Base):
    __tablename__ = "question_variants"
    __table_args__ = (
        Index(
            "ix_question_variants_embedding",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    answer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("answers.id"), index=True)
    question_text: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIM))
    source_job_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("jobs.id"))

    answer: Mapped[Answer] = relationship(back_populates="variants")


class ApplicationAnswer(IdMixin, Base):
    """Exactly what was submitted to each company, per question."""

    __tablename__ = "application_answers"

    job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("jobs.id"), index=True)
    question_text: Mapped[str] = mapped_column(Text)
    answer_submitted: Mapped[str] = mapped_column(Text)
    answer_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("answers.id"))
    answer_version: Mapped[int | None] = mapped_column(Integer)
    match_score: Mapped[float | None] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ProfileVersion(IdMixin, TimestampMixin, Base):
    __tablename__ = "profile_versions"

    version: Mapped[int] = mapped_column(Integer, unique=True)
    facts: Mapped[dict] = mapped_column(JSONB)
    resume_template: Mapped[str | None] = mapped_column(Text)
    note: Mapped[str | None] = mapped_column(Text)


class AppSettings(Base):
    """Single-row settings, edited from the dashboard."""

    __tablename__ = "settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    data: Mapped[dict] = mapped_column(JSONB)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Run(IdMixin, Base):
    __tablename__ = "runs"
    __table_args__ = (
        # Run lock: at most one running row per kind.
        Index(
            "uq_runs_one_running_per_kind",
            "kind",
            unique=True,
            postgresql_where=text("status = 'running'"),
        ),
    )

    kind: Mapped[RunKind] = mapped_column(pg_enum(RunKind, "run_kind"))
    trigger: Mapped[RunTrigger] = mapped_column(pg_enum(RunTrigger, "run_trigger"))
    status: Mapped[RunStatus] = mapped_column(
        pg_enum(RunStatus, "run_status"), default=RunStatus.RUNNING
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    counts: Mapped[dict] = mapped_column(JSONB, default=dict)
    llm_requests: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text)


class RunRequest(IdMixin, Base):
    """Find now / Fly now presses."""

    __tablename__ = "run_requests"

    kind: Mapped[RunKind] = mapped_column(pg_enum(RunKind, "run_kind"))
    source: Mapped[RequestSource] = mapped_column(pg_enum(RequestSource, "request_source"))
    status: Mapped[RequestStatus] = mapped_column(
        pg_enum(RequestStatus, "request_status"), default=RequestStatus.WAITING
    )
    run_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("runs.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    picked_up_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ApplierHeartbeat(Base):
    """Single row, updated every minute by the laptop helper."""

    __tablename__ = "applier_heartbeat"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    version: Mapped[str | None] = mapped_column(String(40))
    busy: Mapped[bool] = mapped_column(Boolean, default=False)


class LlmUsage(Base):
    __tablename__ = "llm_usage"
    __table_args__ = (UniqueConstraint("day", "provider"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    day: Mapped[date] = mapped_column(Date)  # IST calendar day
    provider: Mapped[str] = mapped_column(String(40))
    requests: Mapped[int] = mapped_column(Integer, default=0)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)


class CompanyStatsDaily(Base):
    __tablename__ = "company_stats_daily"
    __table_args__ = (UniqueConstraint("company_id", "day"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id"))
    day: Mapped[date] = mapped_column(Date)
    jobs_found: Mapped[int] = mapped_column(Integer, default=0)
    jobs_matched: Mapped[int] = mapped_column(Integer, default=0)
    jobs_approved: Mapped[int] = mapped_column(Integer, default=0)
    jobs_applied: Mapped[int] = mapped_column(Integer, default=0)
