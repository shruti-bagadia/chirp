"""Enums stored in the database. Pure Python so services and tests can import them."""

from enum import StrEnum

from app.services.ctc import Tier
from app.services.prefilter import LocationFit
from app.services.states import Actor, JobStatus

__all__ = [
    "Actor",
    "AnswerCategory",
    "AnswerType",
    "ApplyMode",
    "CompanyCategory",
    "CompanySource",
    "CompanyState",
    "JobStatus",
    "LocationFit",
    "Pinned",
    "Platform",
    "RequestSource",
    "RequestStatus",
    "RunKind",
    "RunStatus",
    "RunTrigger",
    "Tier",
    "WorkMode",
]


class Platform(StrEnum):
    GREENHOUSE = "greenhouse"
    LEVER = "lever"
    ASHBY = "ashby"
    WORKDAY = "workday"
    SUCCESSFACTORS = "successfactors"
    DARWINBOX = "darwinbox"
    ORACLE = "oracle"
    ICIMS = "icims"
    SMARTRECRUITERS = "smartrecruiters"
    OWN = "own"
    UNKNOWN = "unknown"


class ApplyMode(StrEnum):
    AUTO = "auto"
    QUICK_APPLY = "quick_apply"


class CompanyCategory(StrEnum):
    BANKING_FINTECH = "banking_fintech"
    SERVICES_CONSULTING = "services_consulting"
    PRODUCT_SAAS = "product_saas"
    AI_FIRST = "ai_first"


class CompanyState(StrEnum):
    CANDIDATE = "candidate"
    ACTIVE = "active"
    DORMANT = "dormant"
    BLOCKED = "blocked"


class Pinned(StrEnum):
    NONE = "none"
    HIGH = "high"
    LOW = "low"


class CompanySource(StrEnum):
    SEED = "seed"
    EMAIL_ALERT = "email_alert"
    PASTED_URL = "pasted_url"
    SUGGESTED = "suggested"


class WorkMode(StrEnum):
    HYBRID = "hybrid"
    REMOTE = "remote"
    ONSITE = "onsite"
    UNKNOWN = "unknown"


class AnswerType(StrEnum):
    FIXED = "fixed"
    RULE_BASED = "rule_based"
    PERSONAL = "personal"
    COMPANY_SPECIFIC = "company_specific"


class AnswerCategory(StrEnum):
    LOGISTICS = "logistics"
    COMPENSATION = "compensation"
    BEHAVIORAL = "behavioral"
    TECHNICAL = "technical"
    MOTIVATION = "motivation"
    DIVERSITY = "diversity"


class RunKind(StrEnum):
    FIND = "find"
    PROCESS = "process"
    APPLY = "apply"
    NIGHTLY = "nightly"


class RunStatus(StrEnum):
    RUNNING = "running"
    OK = "ok"
    PARTIAL = "partial"
    FAILED = "failed"


class RunTrigger(StrEnum):
    SCHEDULE = "schedule"
    MANUAL = "manual"


class RequestStatus(StrEnum):
    WAITING = "waiting"
    PICKED_UP = "picked_up"
    DONE = "done"
    SKIPPED = "skipped"


class RequestSource(StrEnum):
    DASHBOARD = "dashboard"
    CLI = "cli"
