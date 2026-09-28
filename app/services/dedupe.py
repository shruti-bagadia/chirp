"""Canonical URLs and dedupe keys, so one job is only ever processed once."""

from __future__ import annotations

import hashlib
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

_TRACKING_PREFIXES = ("utm_",)
_TRACKING_PARAMS = {
    "ref",
    "refid",
    "referrer",
    "source",
    "src",
    "trk",
    "trackingid",
    "fbclid",
    "gclid",
    "mc_cid",
    "mc_eid",
    "lever-source",
    "lever-source[]",
    "lever-origin",
    "gh_src",
    "sourcetype",
    "jobsource",
    "campaign",
}

_ABBREVIATIONS = {
    "sr": "senior",
    "jr": "junior",
    "engg": "engineer",
    "eng": "engineer",
    "dev": "developer",
    "mgr": "manager",
    "ii": "2",
    "iii": "3",
    "i": "1",
}
_LOCATION_NOISE = {"india", "maharashtra", "mh", "in", "hybrid", "onsite"}


def canonical_url(url: str) -> str:
    """Normalize a job URL: lowercase host, drop www, fragment, tracking params, trailing /."""
    parts = urlsplit(url.strip())
    scheme = (parts.scheme or "https").lower()
    host = parts.netloc.lower().removeprefix("www.")
    path = parts.path.rstrip("/") or "/"
    query = sorted(
        (k, v)
        for k, v in parse_qsl(parts.query, keep_blank_values=False)
        if k.lower() not in _TRACKING_PARAMS and not k.lower().startswith(_TRACKING_PREFIXES)
    )
    return urlunsplit((scheme, host, path, urlencode(query), ""))


def _words(text: str) -> list[str]:
    text = text.lower().replace("&", " and ").replace("c++", "cpp").replace(".net", "dotnet")
    return re.findall(r"[a-z0-9]+", text)


def normalize_title(title: str) -> str:
    """'Sr. Backend Engg - II (Python)' -> 'senior backend engineer 2 python'."""
    return " ".join(_ABBREVIATIONS.get(w, w) for w in _words(title))


def normalize_company(name: str) -> str:
    words = [w for w in _words(name) if w not in {"ltd", "limited", "pvt", "private", "inc", "llc"}]
    return " ".join(words)


def normalize_location(location: str) -> str:
    """'Pune, Maharashtra, India' -> 'pune'; 'Remote - India' -> 'remote'."""
    words = [w for w in _words(location) if w not in _LOCATION_NOISE]
    return " ".join(words) or "unknown"


def dedupe_key(company: str, title: str, location: str) -> str:
    raw = "|".join(
        (normalize_company(company), normalize_title(title), normalize_location(location))
    )
    return hashlib.sha256(raw.encode()).hexdigest()[:32]
