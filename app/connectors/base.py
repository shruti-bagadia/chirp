"""Shared types for job-board connectors."""

from __future__ import annotations

import html
import re
from dataclasses import dataclass, field
from datetime import datetime
from html.parser import HTMLParser
from typing import Protocol


class ConnectorError(RuntimeError):
    """A board couldn't be read (network, 4xx/5xx, or unexpected shape)."""


@dataclass(slots=True)
class RawPosting:
    """One job as a platform returns it, normalized just enough to compare across platforms."""

    external_id: str
    title: str
    url: str
    location: str = ""
    description: str = ""
    posted_at: datetime | None = None
    workplace: str | None = None  # "hybrid" | "remote" | "onsite" when the platform says so
    employment: str | None = None  # e.g. "Full-time", "Contract"
    salary_min_lpa: float | None = None
    salary_max_lpa: float | None = None
    extra: dict = field(default_factory=dict)


class Fetcher(Protocol):
    """Anything that can GET (or POST) JSON. The real one uses httpx; tests pass a fake."""

    def get_json(self, url: str, params: dict | None = None) -> dict | list: ...

    def post_json(self, url: str, json_body: dict) -> dict | list: ...


class Connector(Protocol):
    platform: str

    def fetch(self, board_id: str, fetcher: Fetcher) -> list[RawPosting]: ...


class _TextExtractor(HTMLParser):
    BLOCK = {"p", "div", "br", "li", "ul", "ol", "h1", "h2", "h3", "h4", "tr"}

    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in self.BLOCK:
            self.parts.append("\n")
        if tag == "li":
            self.parts.append("• ")

    def handle_data(self, data):
        self.parts.append(data)


def html_to_text(value: str | None) -> str:
    """Job descriptions often arrive as (escaped) HTML. Return readable plain text."""
    if not value:
        return ""
    raw = html.unescape(value)
    parser = _TextExtractor()
    parser.feed(raw)
    text = "".join(parser.parts)
    text = re.sub(r"[ \t\xa0]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n\n", text)
    return text.strip()


def inr_to_lpa(amount: float | int | None, interval: str | None = "year") -> float | None:
    """Convert an INR amount to lakhs per annum."""
    if amount is None:
        return None
    interval = (interval or "year").lower()
    yearly = float(amount) * (12 if "month" in interval else 1)
    return round(yearly / 100_000, 1)


_LPA_RE = re.compile(
    r"(?:₹|inr|rs\.?)?\s*(\d{1,2}(?:\.\d)?)\s*(?:-|–|to)\s*(\d{1,2}(?:\.\d)?)\s*(?:lpa|lakhs?|l\.p\.a)",
    re.I,
)


def salary_from_text(text: str) -> tuple[float | None, float | None]:
    """Find '15-20 LPA' style ranges in a description."""
    m = _LPA_RE.search(text or "")
    if not m:
        return None, None
    low, high = float(m[1]), float(m[2])
    return min(low, high), max(low, high)
