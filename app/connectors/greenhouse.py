"""Greenhouse public Job Board API.

GET https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs?content=true
"""

from __future__ import annotations

from datetime import datetime

from app.connectors.base import Fetcher, RawPosting, html_to_text, salary_from_text

API = "https://boards-api.greenhouse.io/v1/boards/{token}/jobs"


def _dt(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def parse(payload: dict) -> list[RawPosting]:
    out = []
    for job in payload.get("jobs", []):
        description = html_to_text(job.get("content"))
        low, high = salary_from_text(description)
        out.append(
            RawPosting(
                external_id=str(job["id"]),
                title=job.get("title", "").strip(),
                url=job.get("absolute_url", ""),
                location=(job.get("location") or {}).get("name", "") or "",
                description=description,
                posted_at=_dt(job.get("first_published") or job.get("updated_at")),
                salary_min_lpa=low,
                salary_max_lpa=high,
            )
        )
    return out


class GreenhouseConnector:
    platform = "greenhouse"

    def fetch(self, board_id: str, fetcher: Fetcher) -> list[RawPosting]:
        return parse(fetcher.get_json(API.format(token=board_id), {"content": "true"}))
