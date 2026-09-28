"""Fit scoring: prompt, parse, and the small rule-based adjustments."""

from __future__ import annotations

from dataclasses import dataclass

from app.llm import prompts
from app.llm.base import SchemaError
from app.profile.model import Profile

PROMPT_VERSION = "score_v1"
MAX_DESCRIPTION_WORDS = 3000


@dataclass(slots=True)
class JobForLLM:
    title: str
    company: str
    location: str
    work_mode: str
    description: str


@dataclass(slots=True)
class ScoreResult:
    score: int
    must_haves_matched: list[str]
    gaps: list[str]
    seniority_fit: str
    summary: str
    role_focus: str

    @classmethod
    def from_dict(cls, d: dict) -> ScoreResult:
        try:
            score = int(d["score"])
            fit = str(d.get("seniority_fit", "match")).lower()
            if not 0 <= score <= 100:
                raise SchemaError("score must be 0-100")
            if fit not in {"under", "match", "over"}:
                raise SchemaError("seniority_fit must be under, match, or over")
            return cls(
                score=score,
                must_haves_matched=[str(x) for x in d.get("must_haves_matched") or []][:12],
                gaps=[str(x) for x in d.get("gaps") or []][:8],
                seniority_fit=fit,
                summary=str(d.get("summary", "")).strip()[:200],
                role_focus=str(d.get("role_focus", "")).strip()[:80],
            )
        except (KeyError, TypeError, ValueError) as exc:
            if isinstance(exc, SchemaError):
                raise
            raise SchemaError(f"Bad score output: {exc}") from exc


def truncate_words(text: str, limit: int = MAX_DESCRIPTION_WORDS) -> str:
    words = text.split()
    return text if len(words) <= limit else " ".join(words[:limit]) + " …"


def build_prompt(job: JobForLLM, profile: Profile) -> tuple[str, str]:
    system = prompts.load(PROMPT_VERSION).format(years=profile.identity.get("years", ""))
    user = (
        f"JOB\nTitle: {job.title}\nCompany: {job.company}\n"
        f"Location: {job.location} ({job.work_mode})\n\n"
        f"{truncate_words(job.description)}\n\nCANDIDATE FACTS\n{profile.prompt_block()}"
    )
    return system, user


def adjusted_score(result: ScoreResult, work_mode: str) -> int:
    """+5 for Pune hybrid (preferred), −5 for onsite (flagged)."""
    delta = {"hybrid": 5, "onsite": -5}.get(work_mode, 0)
    return max(0, min(100, result.score + delta))
