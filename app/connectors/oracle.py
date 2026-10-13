"""Oracle Fusion HCM "Candidate Experience" public job-search API (Icertis, BNY, ...).

GET https://{host}/hcmRestApi/resources/latest/recruitingCEJobRequisitions
    ?onlyData=true&expand=requisitionList.secondaryLocations
    &finder=findReqs;siteNumber={site},limit={limit},offset={offset},sortBy=POSTING_DATES_DESC

No auth needed — this is the same endpoint the public "Candidate Experience" career site
calls from the browser. Board IDs come from `detect.py` as "{host}/{siteNumber}", e.g.
"iaaviz.fa.ocs.oraclecloud.com/CX_1". The site number isn't visible in a company's normal
careers URL (which uses a human-readable slug like "sites/Jobs-at-Icertis"); it has to be
found once per company (the raw `/sites/{number}/requisitions` form also works and is what
we seed) and from then on the API paginates normally via Offset/Limit.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

from app.connectors.base import ConnectorError, Fetcher, RawPosting

PAGE_SIZE = 25
MAX_PAGES = 20  # 500 jobs; guards against a malformed response looping forever

_WORKPLACE = {"remote": "remote", "hybrid": "hybrid", "onsite": "onsite", "on-site": "onsite"}


def parse_board_id(board_id: str) -> tuple[str, str]:
    """Split "host/siteNumber" back into its parts."""
    host, _, site = (board_id or "").partition("/")
    if not host or not site:
        raise ConnectorError(f"Oracle board ID should look like 'host/siteNumber': {board_id!r}")
    return host, site


def api_url(host: str) -> str:
    return f"https://{host}/hcmRestApi/resources/latest/recruitingCEJobRequisitions"


def job_url(host: str, site: str, req_id: str) -> str:
    return f"https://{host}/hcmUI/CandidateExperience/en/sites/{site}/job/{req_id}"


def _posted_at(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.combine(date.fromisoformat(value), datetime.min.time(), tzinfo=UTC)
    except ValueError:
        return None


def _location(req: dict) -> str:
    primary = (req.get("PrimaryLocation") or "").strip()
    extra = [
        loc.get("Name", "").strip()
        for loc in req.get("secondaryLocations") or []
        if loc.get("Name")
    ]
    return ", ".join([p for p in [primary, *extra] if p])


def parse(payload: dict) -> list[RawPosting]:
    items = payload.get("items") or []
    if not items:
        return []
    item = items[0]
    out = []
    for req in item.get("requisitionList") or []:
        req_id = str(req.get("Id") or "")
        if not req_id:
            continue
        description = "\n\n".join(
            part
            for part in (
                req.get("ExternalQualificationsStr"),
                req.get("ExternalResponsibilitiesStr"),
            )
            if part
        )
        out.append(
            RawPosting(
                external_id=req_id,
                title=(req.get("Title") or "").strip(),
                url="",  # filled in by the connector, which knows host/site
                location=_location(req),
                description=description,
                posted_at=_posted_at(req.get("PostedDate")),
                workplace=_WORKPLACE.get((req.get("WorkplaceType") or "").lower()),
                extra={"requisition_id": req_id},
            )
        )
    return out


class OracleConnector:
    platform = "oracle"

    def fetch(self, board_id: str, fetcher: Fetcher) -> list[RawPosting]:
        host, site = parse_board_id(board_id)
        url = api_url(host)
        out: list[RawPosting] = []
        total: int | None = None
        for page in range(MAX_PAGES):
            offset = page * PAGE_SIZE
            finder = (
                f"findReqs;siteNumber={site},limit={PAGE_SIZE},"
                f"offset={offset},sortBy=POSTING_DATES_DESC"
            )
            params = {
                "onlyData": "true",
                "expand": "requisitionList.secondaryLocations",
                "finder": finder,
            }
            payload = fetcher.get_json(url, params)
            if not isinstance(payload, dict):
                raise ConnectorError(f"Unexpected Oracle response from {url}")
            items = payload.get("items") or []
            if total is None and items:
                total = int(items[0].get("TotalJobsCount") or 0)
            postings = parse(payload)
            for p in postings:
                p.url = job_url(host, site, p.external_id)
            out.extend(postings)
            if len(postings) < PAGE_SIZE or (total is not None and offset + PAGE_SIZE >= total):
                break
        return out
