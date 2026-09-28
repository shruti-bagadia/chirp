"""Rule-based pre-filter. Runs before any LLM call to save quota.

Checks run cheapest-first and stop at the first failure, which becomes the reason
shown under "Filtered out".
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum


class LocationFit(StrEnum):
    PUNE_HYBRID = "pune_hybrid"
    PUNE_ONSITE = "pune_onsite"
    PUNE_UNKNOWN = "pune_unknown"
    REMOTE_INDIA = "remote_india"
    OTHER = "other"


@dataclass(frozen=True, slots=True)
class PrefilterConfig:
    include_titles: tuple[str, ...] = (
        r"back[\s-]?end",
        r"python",
        r"software (development )?engineer",
        r"\bsde\b",
        r"\bai\b",
        r"\bml\b",
        r"machine learning",
        r"\bllm\b",
        r"gen\s?ai",
        r"generative ai",
        r"solutions? engineer",
        r"forward[\s-]deployed",
        r"platform engineer",
        r"\bapis?\b",
        # Titles like Druva's "Senior Staff Software Engineer" already match
        # "software engineer" above; this covers the bare form real postings also
        # use (Mindtickle's "Staff Engineer", no "software" qualifier).
        r"\bstaff engineer\b",
    )
    exclude_titles: tuple[str, ...] = (
        r"front[\s-]?end",
        r"\bui\b",
        r"\bux\b",
        r"\bqa\b",
        r"\btest",
        r"\bsdet\b",
        r"data analyst",
        r"\bsupport\b",
        r"\bintern",
        r"android",
        r"\bios\b",
        r"\breact\b",
        r"angular",
        r"\bsales\b",
        r"engineering manager",
        r"\bprincipal\b",
        r"\bdirector\b",
        r"\barchitect\b",
        # Deliberately NOT excluding "staff": unlike "principal" (reliably senior
        # everywhere), "staff" is used inconsistently in the India market — some
        # product companies use it for 3-5 YOE roles. `parse_experience()` below
        # already rejects on the years actually asked in the posting, which is
        # the precise signal; a blunt title-word match only causes false
        # rejections (e.g. a "Staff Engineer, India" role asking for 3+ years).
    )
    max_experience_years: float = 4
    min_contract_months: int = 6
    max_posting_age_days: int = 7
    allow_pune_onsite: bool = True


@dataclass(slots=True)
class Posting:
    title: str
    location: str
    description: str = ""
    company_blocked: bool = False
    posted_at: datetime | None = None
    salary_max_lpa: float | None = None
    salary_floor_lpa: float | None = None  # floor for this company's tier


@dataclass(slots=True)
class PrefilterResult:
    passed: bool
    reason: str | None = None
    location_fit: LocationFit | None = None
    experience: tuple[float, float | None] | None = None
    flags: list[str] = field(default_factory=list)


_NUM = r"(\d{1,2}(?:\.\d)?)"
_EXP_PATTERNS = (
    re.compile(rf"{_NUM}\s*(?:-|–|to)\s*{_NUM}\s*\+?\s*(?:years|yrs)", re.I),
    re.compile(rf"{_NUM}\s*\+\s*(?:years|yrs)", re.I),
    re.compile(rf"(?:minimum|min\.?|at least|atleast)\s*(?:of\s*)?{_NUM}\s*(?:years|yrs)", re.I),
    re.compile(rf"{_NUM}\s*(?:years|yrs)\s*(?:of\s*)?(?:\w+\s*){{0,4}}experience", re.I),
)


def parse_experience(text: str) -> tuple[float, float | None] | None:
    """Find the experience asked. Returns (min, max) where max may be None ('5+ years')."""
    for i, pattern in enumerate(_EXP_PATTERNS):
        match = pattern.search(text)
        if not match:
            continue
        if i == 0:
            low, high = float(match[1]), float(match[2])
            return (min(low, high), max(low, high))
        return (float(match[1]), None)
    return None


_CONTRACT_RE = re.compile(
    r"(?:contract\w*[^.\n]{0,40}?(\d{1,2})\s*(?:-|\s)?months?)|(?:(\d{1,2})\s*(?:-|\s)?months?\s*contract)",
    re.I,
)


def contract_months(text: str) -> int | None:
    match = _CONTRACT_RE.search(text)
    if not match:
        return None
    return int(match[1] or match[2])


_ONSITE_RE = re.compile(
    r"on[\s-]?site|work from office|\bwfo\b|in[\s-]office|office[\s-]based", re.I
)
_HYBRID_RE = re.compile(r"hybrid", re.I)
_REMOTE_RE = re.compile(r"remote|work from home|\bwfh\b", re.I)
_FOREIGN_RE = re.compile(
    r"\b(usa|united states|uk|united kingdom|london|singapore|dubai|germany|"
    r"canada|australia|emea|us only)\b",
    re.I,
)


def classify_location(location: str, description: str = "") -> LocationFit:
    loc = location.lower()
    both = f"{location}\n{description}"
    if "pune" in loc:
        if _HYBRID_RE.search(both):
            return LocationFit.PUNE_HYBRID
        if _ONSITE_RE.search(both):
            return LocationFit.PUNE_ONSITE
        return LocationFit.PUNE_UNKNOWN
    if _REMOTE_RE.search(loc) and not _FOREIGN_RE.search(loc):
        other_city = re.search(
            r"\b(mumbai|bangalore|bengaluru|hyderabad|chennai|delhi|gurgaon|noida)\b", loc
        )
        if not other_city or "india" in loc or "anywhere" in loc:
            return LocationFit.REMOTE_INDIA
    return LocationFit.OTHER


def _title_ok(title: str, description: str, cfg: PrefilterConfig) -> str | None:
    t = title.lower()
    for pattern in cfg.exclude_titles:
        if re.search(pattern, t):
            return f"Title excluded ({title})"
    if re.search(r"\bjava\b", t) and "python" not in description.lower():
        return "Java role without Python"
    if re.search(r"\.net|dotnet|\bc#", t) and "python" not in description.lower():
        return ".NET role without Python"
    if not any(re.search(p, t) for p in cfg.include_titles):
        return f"Title not a target role ({title})"
    return None


def run_prefilter(posting: Posting, cfg: PrefilterConfig, now: datetime) -> PrefilterResult:
    if posting.company_blocked:
        return PrefilterResult(False, "Company is blocked")

    reason = _title_ok(posting.title, posting.description, cfg)
    if reason:
        return PrefilterResult(False, reason)

    if re.search(r"\bintern(ship)?\b", posting.description, re.I) and re.search(
        r"\bintern", posting.title, re.I
    ):
        return PrefilterResult(False, "Internship")

    exp = parse_experience(f"{posting.title}\n{posting.description}")
    if exp and exp[0] > cfg.max_experience_years:
        return PrefilterResult(False, f"Asks {exp[0]:g}+ years", experience=exp)

    fit = classify_location(posting.location, posting.description)
    if fit == LocationFit.OTHER:
        return PrefilterResult(False, f"Location not Pune or remote India ({posting.location})")
    if fit == LocationFit.PUNE_ONSITE and not cfg.allow_pune_onsite:
        return PrefilterResult(False, "Pune onsite roles are turned off")

    months = contract_months(posting.description)
    if months is not None and months < cfg.min_contract_months:
        return PrefilterResult(False, f"{months}-month contract")

    if (
        posting.salary_max_lpa is not None
        and posting.salary_floor_lpa is not None
        and posting.salary_max_lpa < posting.salary_floor_lpa
    ):
        return PrefilterResult(
            False, f"Pays up to {posting.salary_max_lpa:g} LPA, below your floor"
        )

    if posting.posted_at and now - posting.posted_at > timedelta(days=cfg.max_posting_age_days):
        return PrefilterResult(False, f"Posted over {cfg.max_posting_age_days} days ago")

    flags = ["onsite"] if fit == LocationFit.PUNE_ONSITE else []
    return PrefilterResult(True, None, fit, exp, flags)
