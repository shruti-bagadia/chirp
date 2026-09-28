"""Flexible schedules for Find, Fly, and Nightly runs.

Times are entered and shown in IST. A scheduler tick runs every 15 minutes on
GitHub Actions and asks `due_slot` whether a run should start now.
Missed slots are skipped, never stacked.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30), name="IST")
DAYS: tuple[str, ...] = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
_TIME_RE = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")

# A tick every 15 min can start a few minutes late on GitHub, so allow some grace.
DEFAULT_WINDOW = timedelta(minutes=25)


class ScheduleError(ValueError):
    """Raised for invalid schedule input."""


def parse_time(value: str) -> time:
    """Parse 'HH:MM' (24-hour). Raises ScheduleError with a friendly message."""
    match = _TIME_RE.match(value.strip()) if isinstance(value, str) else None
    if not match:
        raise ScheduleError(f"'{value}' isn't a valid time. Use 24-hour HH:MM, like 08:30.")
    return time(int(match[1]), int(match[2]))


@dataclass(frozen=True, slots=True)
class StepSchedule:
    times: tuple[time, ...]
    days: frozenset[str]

    @classmethod
    def from_dict(cls, data: dict) -> StepSchedule:
        raw_times = data.get("times", [])
        raw_days = data.get("days", [])
        times = tuple(sorted({parse_time(t) for t in raw_times}))
        days = frozenset(d.strip().lower()[:3] for d in raw_days)
        unknown = days - set(DAYS)
        if unknown:
            raise ScheduleError(f"Unknown day(s): {', '.join(sorted(unknown))}.")
        return cls(times=times, days=days)

    def to_dict(self) -> dict:
        return {
            "times": [t.strftime("%H:%M") for t in self.times],
            "days": [d for d in DAYS if d in self.days],
        }


def _as_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        raise ScheduleError("Datetimes must be timezone-aware.")
    return dt.astimezone(UTC)


def slots_on(step: StepSchedule, day_ist: date) -> list[datetime]:
    """All scheduled slots on an IST calendar day, as aware UTC datetimes."""
    if DAYS[day_ist.weekday()] not in step.days:
        return []
    return [datetime.combine(day_ist, t, tzinfo=IST).astimezone(UTC) for t in step.times]


def next_run(step: StepSchedule, now: datetime, *, paused: bool = False) -> datetime | None:
    """The next slot strictly after `now`, or None if paused or nothing is scheduled."""
    if paused or not step.times or not step.days:
        return None
    now_utc = _as_utc(now)
    today = now_utc.astimezone(IST).date()
    for offset in range(8):
        for slot in slots_on(step, today + timedelta(days=offset)):
            if slot > now_utc:
                return slot
    return None


def due_slot(
    step: StepSchedule,
    now: datetime,
    *,
    last_started: datetime | None,
    paused: bool = False,
    window: timedelta = DEFAULT_WINDOW,
) -> datetime | None:
    """Return the slot that should start right now, if any.

    A slot is due when it's in the past but within `window`, and no run of this kind has
    started at or after it. Older slots are skipped rather than stacked up.
    """
    if paused:
        return None
    now_utc = _as_utc(now)
    last = _as_utc(last_started) if last_started else None
    today = now_utc.astimezone(IST).date()
    candidates = slots_on(step, today - timedelta(days=1)) + slots_on(step, today)
    due = [s for s in candidates if s <= now_utc < s + window]
    if not due:
        return None
    slot = max(due)
    if last is not None and last >= slot:
        return None
    return slot


def format_ist(dt: datetime, now: datetime | None = None) -> str:
    """'1:00 PM', or '8:30 AM tomorrow', or 'Mon 8:30 AM' for friendly display."""
    local = _as_utc(dt).astimezone(IST)
    label = local.strftime("%I:%M %p").lstrip("0")
    if now is None:
        return label
    today = _as_utc(now).astimezone(IST).date()
    if local.date() == today:
        return label
    if local.date() == today + timedelta(days=1):
        return f"{label} tomorrow"
    return f"{local.strftime('%a')} {label}"
