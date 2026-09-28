"""Reads job-alert emails and adds unseen companies as Candidates. P1 — see
docs/08_company_registry.md §2A. Needs `GMAIL_CLIENT_ID`/`GMAIL_CLIENT_SECRET`/
`GMAIL_REFRESH_TOKEN` set (a Google Cloud OAuth app + a completed consent flow on
Shruti's own Gmail) before `run_gmail_sync` does anything but raise `GmailError`.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.connectors.detect import detect
from app.connectors.gmail_alerts import (
    GmailClient,
    extract_application,
    extract_ats_links,
    extract_company_names,
)
from app.db.enums import ManualApplicationSource, Platform
from app.db.models import ManualApplication
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


def run_manual_application_sync(
    db: Session, client: GmailClient, label: str = "applications-sent"
) -> dict:
    """Reads "your application was sent/received" confirmation emails and logs
    each as a `manual_applications` row (source=gmail), for jobs applied to
    outside Chirp entirely. Dedupes on `gmail_message_id`, so re-running (this
    runs alongside `run_gmail_sync` in the nightly worker) never double-counts.
    Shruti tracks every other status (callback, etc.) by hand from there.
    """
    counts = {"emails": 0, "added": 0, "already_known": 0}
    seen = set(
        db.scalars(
            select(ManualApplication.gmail_message_id).where(
                ManualApplication.gmail_message_id.is_not(None)
            )
        )
    )
    for email in client.list_alert_emails(label):
        counts["emails"] += 1
        if email.message_id in seen:
            counts["already_known"] += 1
            continue
        company, title = extract_application(email.subject, email.html_body)
        db.add(
            ManualApplication(
                company=company,
                title=title,
                applied_at=email.received_at or datetime.now(UTC),
                source=ManualApplicationSource.GMAIL,
                gmail_message_id=email.message_id,
            )
        )
        counts["added"] += 1
    db.commit()
    return counts
