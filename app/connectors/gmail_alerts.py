"""Job-alert email discovery (P1). Read-only, one Gmail label, no scraping of any
job board itself — see docs/08_company_registry.md §2A.

`extract_ats_links`/`extract_company_names` are pure and tested against fixture
HTML. `GmailClient` needs a Google Cloud OAuth app (`GMAIL_CLIENT_ID`/
`GMAIL_CLIENT_SECRET`/`GMAIL_REFRESH_TOKEN`) before any of its HTTP calls will
work — that setup, and the Gmail label/filter itself, has to happen on Shruti's
Google account; nothing here can be verified end-to-end without it. Uses plain
`httpx` REST calls rather than Google's client libraries, to avoid a heavy
dependency for three simple endpoints.
"""

from __future__ import annotations

import base64
import re
from dataclasses import dataclass

import httpx

from app.connectors.base import html_to_text

TOKEN_URL = "https://oauth2.googleapis.com/token"  # noqa: S105 - a URL, not a secret
API = "https://gmail.googleapis.com/gmail/v1/users/me"

# Links that `app.connectors.detect` already knows how to fingerprint. Only these
# are confident enough to auto-create a company from — a bare company *name*
# mentioned in alert-email prose (see `extract_company_names`) is a weaker signal.
_ATS_LINK_RE = re.compile(
    r'href="(https?://[^"#]*(?:greenhouse\.io|jobs\.lever\.co|jobs\.ashbyhq\.com'
    r"|myworkdayjobs\.com|successfactors\.com|darwinbox\.[a-z]+|oraclecloud\.com"
    r'|taleo\.net|icims\.com|smartrecruiters\.com)[^"]*)"',
    re.I,
)
_AT_COMPANY_RE = re.compile(r"\bat\s+([A-Z][\w&.,' -]{1,60}?)(?=\s*(?:[.!]|$|\s-\s|\n))")
_STOPWORDS = {"the", "a", "an", "your", "new", "this", "click", "here", "home"}


class GmailError(RuntimeError):
    pass


@dataclass(slots=True)
class AlertEmail:
    message_id: str
    subject: str
    html_body: str


def extract_ats_links(html_body: str) -> list[str]:
    """De-duplicated job-board links whose host `detect()` recognizes."""
    seen: dict[str, None] = {}
    for url in _ATS_LINK_RE.findall(html_body):
        seen.setdefault(url, None)
    return list(seen)


def extract_company_names(html_body: str) -> list[str]:
    """Best-effort "... at <Company> ..." extraction from alert-email prose, for
    companies with no recognizable ATS link in the same email. Deliberately
    favors precision over recall — a missed company is a no-op, not a problem;
    a wrong one just becomes an easily-rejected Candidate, never auto-applied to.
    """
    text = html_to_text(html_body)
    out: list[str] = []
    seen: set[str] = set()
    for m in _AT_COMPANY_RE.finditer(text):
        name = m.group(1).strip().rstrip(".,-")
        key = name.lower()
        if not name or key in _STOPWORDS or key in seen or len(name.split()) > 6:
            continue
        seen.add(key)
        out.append(name)
    return out


def _b64url_decode(data: str) -> str:
    padded = data + "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(padded).decode("utf-8", errors="replace")


def _extract_html(payload: dict) -> str:
    """Gmail nests MIME parts arbitrarily; find the first text/html part."""

    def walk(part: dict) -> str | None:
        if part.get("mimeType") == "text/html" and part.get("body", {}).get("data"):
            return _b64url_decode(part["body"]["data"])
        for sub in part.get("parts") or []:
            found = walk(sub)
            if found:
                return found
        return None

    return walk(payload) or ""


def _header(payload: dict, name: str) -> str:
    for h in payload.get("headers") or []:
        if h.get("name", "").lower() == name.lower():
            return h.get("value", "")
    return ""


class GmailClient:
    """Thin wrapper over the three Gmail REST calls this needs. Unverified against
    a real account — there's no way to do that without Shruti's own OAuth setup."""

    def __init__(self, client_id: str, client_secret: str, refresh_token: str) -> None:
        if not (client_id and client_secret and refresh_token):
            raise GmailError(
                "GMAIL_CLIENT_ID/GMAIL_CLIENT_SECRET/GMAIL_REFRESH_TOKEN aren't all set."
            )
        self._client_id = client_id
        self._client_secret = client_secret
        self._refresh_token = refresh_token
        self._access_token: str | None = None
        self._http = httpx.Client(timeout=20)

    def _authed_get(self, url: str, params: dict | None = None) -> dict:
        if self._access_token is None:
            self._refresh_access_token()
        r = self._http.get(
            url, params=params, headers={"Authorization": f"Bearer {self._access_token}"}
        )
        if r.status_code == 401:  # token expired mid-run; refresh once and retry
            self._refresh_access_token()
            r = self._http.get(
                url, params=params, headers={"Authorization": f"Bearer {self._access_token}"}
            )
        if r.status_code != 200:
            raise GmailError(f"Gmail API error {r.status_code}: {r.text[:300]}")
        return r.json()

    def _refresh_access_token(self) -> None:
        r = self._http.post(
            TOKEN_URL,
            data={
                "client_id": self._client_id,
                "client_secret": self._client_secret,
                "refresh_token": self._refresh_token,
                "grant_type": "refresh_token",
            },
        )
        if r.status_code != 200:
            raise GmailError(f"Gmail token refresh failed: {r.status_code} {r.text[:300]}")
        self._access_token = r.json()["access_token"]

    def _label_id(self, label_name: str) -> str | None:
        labels = self._authed_get(f"{API}/labels").get("labels", [])
        return next((label["id"] for label in labels if label["name"] == label_name), None)

    def list_alert_emails(self, label_name: str, max_results: int = 25) -> list[AlertEmail]:
        label_id = self._label_id(label_name)
        if label_id is None:
            return []  # the label doesn't exist yet — nothing to read, not an error
        listing = self._authed_get(
            f"{API}/messages", params={"labelIds": label_id, "maxResults": max_results}
        )
        out = []
        for stub in listing.get("messages", []):
            msg = self._authed_get(f"{API}/messages/{stub['id']}", params={"format": "full"})
            out.append(
                AlertEmail(
                    message_id=msg["id"],
                    subject=_header(msg["payload"], "Subject"),
                    html_body=_extract_html(msg["payload"]),
                )
            )
        return out

    def close(self) -> None:
        self._http.close()
