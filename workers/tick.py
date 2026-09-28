"""Scheduler tick (every 15 min on GitHub Actions): start a Find run if one is due."""

from __future__ import annotations

import sys
from datetime import UTC, datetime

from sqlalchemy import select

from app.connectors.http import HttpFetcher
from app.core.defaults import DEFAULT_SETTINGS
from app.core.logging import setup_logging
from app.db.enums import RunKind, RunTrigger
from app.db.models import AppSettings, Run
from app.db.session import get_sessionmaker
from app.services.schedule import StepSchedule, due_slot
from workers.finder import run_find
from workers.processor import run_process


def main() -> int:
    setup_logging()
    now = datetime.now(UTC)
    with get_sessionmaker()() as db:
        row = db.get(AppSettings, 1)
        schedule = (row.data if row else DEFAULT_SETTINGS)["schedule"]
        last = db.scalar(
            select(Run.started_at).where(Run.kind == RunKind.FIND).order_by(Run.started_at.desc())
        )
        slot = due_slot(
            StepSchedule.from_dict(schedule["find"]),
            now,
            last_started=last,
            paused=schedule.get("paused", False),
        )
        if slot is None:
            print("Nothing due.")
            return 0
        fetcher = HttpFetcher()
        try:
            run = run_find(db, fetcher, trigger=RunTrigger.SCHEDULE, now=now)
        finally:
            fetcher.close()
        print(f"Find for {slot:%H:%M} UTC: {run.status.value if run else 'already running'}")
        if run is not None:
            print(f"Process: {run_process(db, trigger=RunTrigger.SCHEDULE)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
