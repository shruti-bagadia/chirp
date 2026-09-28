"""Reads job-alert emails and adds unseen companies as Candidates. P1 — see
docs/08_company_registry.md §2A. Needs `GMAIL_CLIENT_ID`/`GMAIL_CLIENT_SECRET`/
`GMAIL_REFRESH_TOKEN` set (a Google Cloud OAuth app + a completed consent flow on
Shruti's own Gmail) before `run_gmail_sync` does anything but raise `GmailError`.
"""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.connectors.detect import detect
from app.connectors.gmail_alerts import GmailClient, extract_ats_links, extract_company_names
from app.db.enums import Platform
from app.services.companies import add_candidate_from_email

log = logging.getLogger("chirp.gmail_sync")


def run_gmail_sync(db: Session, client: GmailClient, label: str = "job-alerts") -> dict:
    counts = {"emails": 0, "added_from_links": 0, "added_from_names": 0, "already_known": 0}
    for email in client.list_alert_emails(label):
        counts["emails"] += 1
        added_names: set[str] = set()

        for url in extract_ats_links(email.html_body):
            d = detect(url)
            if d.platform == Platform.UNKNOWN:
                continue
            guessed_name = (d.board_id or url).split("/")[0].replace("-", " ").title()
            company = add_candidate_from_email(db, guessed_name, url=url)
            if company is None:
                counts["already_known"] += 1
            else:
                counts["added_from_links"] += 1
                added_names.add(guessed_name.lower())

        for name in extract_company_names(email.html_body):
            if name.lower() in added_names:
                continue  # already added from a link in this same email
            company = add_candidate_from_email(db, name)
            if company is None:
                counts["already_known"] += 1
            else:
                counts["added_from_names"] += 1
    return counts
