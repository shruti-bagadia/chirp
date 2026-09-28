"""Work out which job platform a careers URL uses, and its board ID."""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import parse_qs, urlsplit

from app.db.enums import ApplyMode, Platform

AUTO_APPLY = {Platform.GREENHOUSE, Platform.LEVER, Platform.ASHBY}


@dataclass(frozen=True, slots=True)
class Detection:
    platform: Platform
    board_id: str | None
    apply_mode: ApplyMode

    @classmethod
    def of(cls, platform: Platform, board_id: str | None = None) -> Detection:
        mode = ApplyMode.AUTO if platform in AUTO_APPLY else ApplyMode.QUICK_APPLY
        return cls(platform, board_id, mode)


_FIRST = r"/([A-Za-z0-9_.-]+)"


def from_url(url: str) -> Detection | None:
    parts = urlsplit(url.strip() if "://" in url else f"https://{url.strip()}")
    host, path = parts.netloc.lower(), parts.path

    if host.endswith("greenhouse.io"):
        qs = parse_qs(parts.query)
        if "for" in qs:  # embed/job_board?for=token
            return Detection.of(Platform.GREENHOUSE, qs["for"][0])
        m = re.match(_FIRST, path)
        if m and m[1] not in {"embed", "v1"}:
            return Detection.of(Platform.GREENHOUSE, m[1])
        return Detection.of(Platform.GREENHOUSE)
    if host in {"jobs.lever.co", "jobs.eu.lever.co"}:
        m = re.match(_FIRST, path)
        return Detection.of(Platform.LEVER, m[1] if m else None)
    if host == "jobs.ashbyhq.com":
        m = re.match(_FIRST, path)
        return Detection.of(Platform.ASHBY, m[1] if m else None)
    m = re.match(r"^([a-z0-9-]+)\.(wd\d+)\.myworkdayjobs\.com$", host)
    if m:
        segs = [s for s in path.split("/") if s]
        if segs and re.fullmatch(r"[a-z]{2}-[A-Z]{2}", segs[0]):
            segs = segs[1:]  # drop locale like en-US
        site = segs[0] if segs else None
        return Detection.of(Platform.WORKDAY, f"{m[1]}/{m[2]}/{site}" if site else None)
    if (
        "successfactors" in host
        or host.startswith("career")
        and ".sap" in host
        or "jobs.sap.com" in host
    ):
        return Detection.of(Platform.SUCCESSFACTORS)
    if "darwinbox" in host:
        return Detection.of(Platform.DARWINBOX)
    if "oraclecloud.com" in host or "taleo.net" in host:
        return Detection.of(Platform.ORACLE)
    if "icims.com" in host:
        return Detection.of(Platform.ICIMS)
    if "smartrecruiters.com" in host:
        segs = [s for s in path.split("/") if s]
        return Detection.of(Platform.SMARTRECRUITERS, segs[0] if segs else None)
    return None


_EMBEDS = [
    (
        Platform.GREENHOUSE,
        re.compile(
            r"boards(?:-api)?\.greenhouse\.io/(?:embed/job_board(?:/js)?\?for=|v1/boards/)?([A-Za-z0-9_-]+)"
        ),
    ),
    (Platform.LEVER, re.compile(r"(?:jobs|api)\.lever\.co/(?:v0/postings/)?([A-Za-z0-9_.-]+)")),
    (Platform.ASHBY, re.compile(r"jobs\.ashbyhq\.com/([A-Za-z0-9_.-]+)")),
    (Platform.WORKDAY, re.compile(r"https?://([a-z0-9-]+\.wd\d+\.myworkdayjobs\.com/[^\s\"'<>]+)")),
]


def from_html(page: str) -> Detection | None:
    """For companies on their own domain: look for embedded boards in the page source."""
    for platform, pattern in _EMBEDS:
        m = pattern.search(page)
        if not m:
            continue
        if platform == Platform.WORKDAY:
            return from_url("https://" + m[1])
        if m[1] in {"embed", "js", "v0", "v1"}:
            continue
        return Detection.of(platform, m[1])
    return None


def detect(url: str, page_html: str | None = None) -> Detection:
    return (
        from_url(url)
        or (from_html(page_html) if page_html else None)
        or Detection.of(Platform.OWN if page_html else Platform.UNKNOWN)
    )
