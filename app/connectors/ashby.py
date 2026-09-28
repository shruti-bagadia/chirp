"""Ashby public Job Posting API.

GET https://api.ashbyhq.com/posting-api/job-board/{board}?includeCompensation=true
"""

from __future__ import annotations

from datetime import datetime

from app.connectors.base import Fetcher, RawPosting, html_to_text, salary_from_text

API = "https://api.ashbyhq.com/posting-api/job-board/{board}"


def _dt(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value.replace("Z", "+00:00")) if value else None


def parse(payload: dict) -> list[RawPosting]:
    out = []
    for job in payload.get("jobs", []):
        if job.get("isListed") is False:
            continue
        description = job.get("descriptionPlain") or html_to_text(job.get("descriptionHtml"))
        low, high = salary_from_text(description)
        workplace = (job.get("workplaceType") or "").lower() or (
            "remote" if job.get("isRemote") else None
        )
        out.append(
            RawPosting(
                external_id=str(job.get("id") or job.get("jobUrl")),
                title=(job.get("title") or "").strip(),
                url=job.get("jobUrl") or job.get("applyUrl") or "",
                location=job.get("location") or "",
                description=description,
                posted_at=_dt(job.get("publishedAt")),
                workplace=workplace or None,
                employment=job.get("employmentType"),
                salary_min_lpa=low,
                salary_max_lpa=high,
                extra={"apply_url": job.get("applyUrl")},
            )
        )
    return out


class AshbyConnector:
    platform = "ashby"

    def fetch(self, board_id: str, fetcher: Fetcher) -> list[RawPosting]:
        return parse(fetcher.get_json(API.format(board=board_id), {"includeCompensation": "true"}))
