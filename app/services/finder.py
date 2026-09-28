"""Turn raw postings into new jobs: dedupe, classify, and pre-filter. Pure logic, no I/O."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from app.connectors.base import RawPosting
from app.services.ctc import DEFAULT_BANDS, Tier, TierBand
from app.services.dedupe import canonical_url, dedupe_key
from app.services.prefilter import LocationFit, Posting, PrefilterConfig, run_prefilter
from app.services.schedule import IST
from app.services.states import JobStatus

_FIT_TO_MODE = {
    LocationFit.PUNE_HYBRID: "hybrid",
    LocationFit.PUNE_ONSITE: "onsite",
    LocationFit.REMOTE_INDIA: "remote",
}


@dataclass(slots=True)
class CompanyRef:
    id: object
    name: str
    tier: Tier = Tier.STANDARD
    blocked: bool = False


@dataclass(slots=True)
class NewJob:
    company_id: object
    external_id: str
    url: str
    apply_url: str | None
    canonical_url: str
    dedupe_key: str
    title: str
    location: str
    description: str
    work_mode: str
    posted_at: datetime | None
    salary_min_lpa: float | None
    salary_max_lpa: float | None
    experience_min: float | None
    experience_max: float | None
    status: JobStatus
    status_reason: str | None
    flags: list[str]
    batch: str


@dataclass(slots=True)
class FinderOutcome:
    jobs: list[NewJob] = field(default_factory=list)
    duplicates: int = 0

    @property
    def kept(self) -> int:
        return sum(1 for j in self.jobs if j.status == JobStatus.DISCOVERED)

    @property
    def filtered(self) -> int:
        return sum(1 for j in self.jobs if j.status == JobStatus.FILTERED_OUT)


def batch_label(now: datetime) -> str:
    local = now.astimezone(IST)
    return f"{local:%Y-%m-%d} {'AM' if local.hour < 12 else 'PM'}"


def _location_for_rules(p: RawPosting) -> str:
    """Platforms often put hybrid/remote in a separate field; fold it into the location."""
    if p.workplace and p.workplace.lower() not in p.location.lower():
        return f"{p.location} ({p.workplace})".strip()
    return p.location


def _description_for_rules(p: RawPosting) -> str:
    extra = f"\nEmployment: {p.employment}" if p.employment else ""
    return p.description + extra


def process_postings(
    company: CompanyRef,
    postings: list[RawPosting],
    *,
    seen_urls: set[str],
    seen_keys: set[str],
    now: datetime,
    cfg: PrefilterConfig | None = None,
    bands: dict[Tier, TierBand] | None = None,
) -> FinderOutcome:
    """Dedupe against `seen_*` (updated in place), then pre-filter what's new."""
    cfg = cfg or PrefilterConfig()
    band = (bands or DEFAULT_BANDS)[Tier(company.tier)]
    batch = batch_label(now)
    out = FinderOutcome()

    for p in postings:
        if not p.url or not p.title:
            continue
        url = canonical_url(p.url)
        key = dedupe_key(company.name, p.title, p.location)
        if url in seen_urls or key in seen_keys:
            out.duplicates += 1
            continue
        seen_urls.add(url)
        seen_keys.add(key)

        result = run_prefilter(
            Posting(
                title=p.title,
                location=_location_for_rules(p),
                description=_description_for_rules(p),
                company_blocked=company.blocked,
                posted_at=p.posted_at,
                salary_max_lpa=p.salary_max_lpa,
                salary_floor_lpa=band.floor,
            ),
            cfg,
            now,
        )
        exp = result.experience or (None, None)
        mode = _FIT_TO_MODE.get(result.location_fit, (p.workplace or "unknown").lower())
        if mode not in {"hybrid", "remote", "onsite"}:
            mode = "unknown"
        out.jobs.append(
            NewJob(
                company_id=company.id,
                external_id=p.external_id,
                url=p.url,
                apply_url=p.extra.get("apply_url") or None,
                canonical_url=url,
                dedupe_key=key,
                title=p.title,
                location=p.location,
                description=p.description,
                work_mode=mode,
                posted_at=p.posted_at,
                salary_min_lpa=p.salary_min_lpa,
                salary_max_lpa=p.salary_max_lpa,
                experience_min=exp[0],
                experience_max=exp[1],
                status=JobStatus.DISCOVERED if result.passed else JobStatus.FILTERED_OUT,
                status_reason=result.reason,
                flags=result.flags,
                batch=batch,
            )
        )
    return out
