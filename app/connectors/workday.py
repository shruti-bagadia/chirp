"""Workday public job-search API (used by every *.myworkdayjobs.com careers site; no auth).

POST https://{tenant}.{wd}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs
Body: {"appliedFacets": {}, "limit": 20, "offset": 0, "searchText": ""}

Board IDs come from `detect.py` as "{tenant}/{wd}/{site}", e.g. "mastercard/wd1/CorporateCareers".

Things observed on real tenants (Sep 2026):
- `limit` above 20 returns HTTP 400, so we page 20 at a time.
- `total` is only filled in on the first page; later pages report `total: 0`.
- `locationsText` is missing on some tenants (e.g. Accenture), where the location is the
  second entry of `bulletFields` instead. `bulletFields[0]` is usually the requisition ID.
- The list endpoint has no description and no exact date, only fuzzy text like
  "Posted 3 Days Ago". See `posted_at_from_text`.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta

from app.connectors.base import ConnectorError, Fetcher, RawPosting

PAGE_SIZE = 20  # Workday rejects anything larger
MAX_PAGES = 25  # 500 jobs; guards against a malformed response looping forever

_DAYS_AGO = re.compile(r"(\d+)\+?\s*days?\s+ago", re.I)


def parse_board_id(board_id: str) -> tuple[str, str, str]:
    """Split "tenant/wd1/Site" back into its parts."""
    parts = [p for p in (board_id or "").strip().split("/") if p]
    if len(parts) != 3 or not re.fullmatch(r"wd\d+", parts[1]):
        raise ConnectorError(f"Workday board ID should look like 'tenant/wd1/Site': {board_id!r}")
    return parts[0], parts[1], parts[2]


def api_url(board_id: str) -> str:
    tenant, wd, site = parse_board_id(board_id)
    return f"https://{tenant}.{wd}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs"


def job_url(board_id: str, external_path: str) -> str:
    tenant, wd, site = parse_board_id(board_id)
    return f"https://{tenant}.{wd}.myworkdayjobs.com/{site}{external_path}"


def posted_at_from_text(text: str | None, now: datetime | None = None) -> datetime | None:
    """Turn Workday's "Posted 3 Days Ago" into an approximate UTC datetime.

    This is deliberately approximate. The exact date needs one extra GET per job to the detail
    endpoint, which would roughly double our requests per board; day-level accuracy is enough
    for freshness sorting. "Posted 30+ Days Ago" becomes now - 30 days (a lower bound on age).
    """
    if not text:
        return None
    now = now or datetime.now(UTC)
    t = text.strip().lower()
    if "today" in t or "just posted" in t:
        return now
    if "yesterday" in t:
        return now - timedelta(days=1)
    m = _DAYS_AGO.search(t)
    if m:
        return now - timedelta(days=int(m[1]))
    return None


def _location(job: dict) -> str:
    if job.get("locationsText"):
        return job["locationsText"]
    bullets = job.get("bulletFields") or []
    if len(bullets) > 1:
        return ", ".join(str(b) for b in bullets[1:])
    return ""


def parse(payload: dict, board_id: str, now: datetime | None = None) -> list[RawPosting]:
    out = []
    for job in payload.get("jobPostings") or []:
        path = job.get("externalPath") or ""
        if not path:
            continue
        remote = (job.get("remoteType") or "").lower()
        workplace = next((w for w in ("hybrid", "remote", "onsite") if w in remote), None)
        if workplace is None and "on-site" in remote:
            workplace = "onsite"
        out.append(
            RawPosting(
                external_id=str(job.get("jobReqId") or path.rstrip("/").rsplit("/", 1)[-1]),
                title=(job.get("title") or "").strip(),
                url=job_url(board_id, path),
                location=_location(job),
                description="",  # not in the list endpoint; scoring copes with an empty one
                posted_at=posted_at_from_text(job.get("postedOn"), now),
                workplace=workplace,
                extra={"posted_on": job.get("postedOn"), "bullet_fields": job.get("bulletFields")},
            )
        )
    return out


class WorkdayConnector:
    platform = "workday"

    def __init__(self, search_text: str = "") -> None:
        self.search_text = search_text

    def fetch(self, board_id: str, fetcher: Fetcher) -> list[RawPosting]:
        url = api_url(board_id)
        now = datetime.now(UTC)
        out: list[RawPosting] = []
        total: int | None = None
        for page in range(MAX_PAGES):
            offset = page * PAGE_SIZE
            body = {
                "appliedFacets": {},
                "limit": PAGE_SIZE,
                "offset": offset,
                "searchText": self.search_text,
            }
            payload = fetcher.post_json(url, body)
            if not isinstance(payload, dict):
                raise ConnectorError(f"Unexpected Workday response from {url}")
            if total is None:  # only the first page carries a real total
                total = int(payload.get("total") or 0)
            postings = payload.get("jobPostings") or []
            out.extend(parse(payload, board_id, now))
            if len(postings) < PAGE_SIZE or offset + PAGE_SIZE >= total:
                break
        return out
