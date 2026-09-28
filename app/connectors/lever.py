"""Lever public Postings API.

GET https://api.lever.co/v0/postings/{company}?mode=json
"""

from __future__ import annotations

from datetime import UTC, datetime

from app.connectors.base import Fetcher, RawPosting, html_to_text, inr_to_lpa, salary_from_text

API = "https://api.lever.co/v0/postings/{company}"


def _description(job: dict) -> str:
    parts = [job.get("descriptionPlain") or ""]
    for block in job.get("lists") or []:
        parts.append(block.get("text", ""))
        parts.append(block.get("content", ""))
    parts.append(job.get("additionalPlain") or "")
    return html_to_text("\n".join(p for p in parts if p))


def parse(payload: list) -> list[RawPosting]:
    out = []
    for job in payload or []:
        cats = job.get("categories") or {}
        description = _description(job)
        low = high = None
        salary = job.get("salaryRange") or {}
        if (salary.get("currency") or "").upper() == "INR":
            low = inr_to_lpa(salary.get("min"), salary.get("interval"))
            high = inr_to_lpa(salary.get("max"), salary.get("interval"))
        if high is None:
            low, high = salary_from_text(description)
        created = job.get("createdAt")
        out.append(
            RawPosting(
                external_id=str(job["id"]),
                title=(job.get("text") or "").strip(),
                url=job.get("hostedUrl") or job.get("applyUrl") or "",
                location=cats.get("location") or ", ".join(cats.get("allLocations") or []),
                description=description,
                posted_at=datetime.fromtimestamp(created / 1000, tz=UTC) if created else None,
                workplace=(job.get("workplaceType") or None),
                employment=cats.get("commitment"),
                salary_min_lpa=low,
                salary_max_lpa=high,
                extra={"apply_url": job.get("applyUrl")},
            )
        )
    return out


class LeverConnector:
    platform = "lever"

    def fetch(self, board_id: str, fetcher: Fetcher) -> list[RawPosting]:
        return parse(fetcher.get_json(API.format(company=board_id), {"mode": "json"}))
