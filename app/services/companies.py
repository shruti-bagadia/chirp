"""Company registry operations (database)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.connectors.detect import detect
from app.connectors.seed import SEED_COMPANIES
from app.db.enums import CompanySource, CompanyState, Pinned, Tier
from app.db.models import Company
from app.services.dedupe import normalize_company


def find_by_name(db: Session, name: str) -> Company | None:
    target = normalize_company(name)
    for c in db.scalars(select(Company)):
        if normalize_company(c.name) == target or target in {
            normalize_company(a) for a in c.aliases or []
        }:
            return c
    return None


def seed(db: Session) -> int:
    """Insert seed companies that don't exist yet. Returns how many were added."""
    added = 0
    for row in SEED_COMPANIES:
        if find_by_name(db, row["name"]):
            continue
        company = Company(
            name=row["name"],
            tier=row.get("tier", Tier.STANDARD),
            category=row.get("category"),
            state=row.get("state", CompanyState.ACTIVE),
            pinned=row.get("pinned", Pinned.NONE),
            source=CompanySource.SEED,
        )
        if url := row.get("careers_url"):
            d = detect(url)
            company.careers_url = url
            company.platform = d.platform
            company.platform_board_id = d.board_id
            company.apply_mode = d.apply_mode
        # Rows without a URL keep the model defaults (Platform.UNKNOWN, ApplyMode.QUICK_APPLY).
        db.add(company)
        added += 1
    db.commit()
    return added


def add_from_url(
    db: Session,
    url: str,
    *,
    name: str | None = None,
    tier: Tier = Tier.STANDARD,
    page_html: str | None = None,
) -> Company:
    """Create or update a company from its careers URL, detecting the platform."""
    d = detect(url, page_html)
    company = find_by_name(db, name) if name else None
    if company is None:
        guessed = name or (d.board_id or url).split("/")[0].replace("-", " ").title()
        company = Company(
            name=guessed, tier=tier, state=CompanyState.ACTIVE, source=CompanySource.PASTED_URL
        )
        db.add(company)
    company.careers_url = url
    company.platform = d.platform
    company.platform_board_id = d.board_id
    company.apply_mode = d.apply_mode
    if company.state == CompanyState.CANDIDATE:
        company.state = CompanyState.ACTIVE
    db.commit()
    return company


def add_candidate_from_email(
    db: Session,
    name: str,
    *,
    url: str | None = None,
    aliases: list[str] | None = None,
) -> Company | None:
    """A company mentioned in a job-alert email becomes a Candidate — unlike
    `add_from_url` (a deliberate human action, goes straight to Active), an
    email-sourced discovery always waits for your yes/no. Returns None if the
    company (or an alias of it) is already known, so re-syncing is a no-op.
    """
    existing = find_by_name(db, name)
    if existing is not None:
        return None
    company = Company(name=name, aliases=aliases or [], source=CompanySource.EMAIL_ALERT)
    if url:
        d = detect(url)
        company.careers_url = url
        company.platform = d.platform
        company.platform_board_id = d.board_id
        company.apply_mode = d.apply_mode
    db.add(company)
    db.commit()
    return company


def scan_order(db: Session) -> list[Company]:
    """Active companies with a readable board, pinned-high first, pinned-low last."""
    rank = {Pinned.HIGH: 0, Pinned.NONE: 1, Pinned.LOW: 2}
    rows = db.scalars(select(Company).where(Company.state == CompanyState.ACTIVE)).all()
    return sorted(rows, key=lambda c: (rank[c.pinned], -c.priority_score, c.name))
