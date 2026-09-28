from datetime import UTC, datetime, timedelta

import pytest

from app.services.schedule import (
    IST,
    ScheduleError,
    StepSchedule,
    due_slot,
    format_ist,
    next_run,
    parse_time,
)

WEEKDAYS = ["mon", "tue", "wed", "thu", "fri"]


def ist(y, m, d, hh, mm):
    return datetime(y, m, d, hh, mm, tzinfo=IST)


def step(times, days=WEEKDAYS):
    return StepSchedule.from_dict({"times": times, "days": days})


# 2026-09-28 is a Monday.
MON = (2026, 9, 28)


def test_parse_time_valid_and_invalid():
    assert parse_time("08:30").hour == 8
    for bad in ["25:00", "9am", "8:3", "", "24:00"]:
        with pytest.raises(ScheduleError):
            parse_time(bad)


def test_unknown_day_rejected():
    with pytest.raises(ScheduleError):
        StepSchedule.from_dict({"times": ["08:30"], "days": ["funday"]})


def test_round_trip_dict_sorted_and_deduped():
    s = step(["13:00", "08:30", "08:30"])
    assert s.to_dict() == {"times": ["08:30", "13:00"], "days": WEEKDAYS}


def test_next_run_later_today():
    s = step(["08:30", "13:00"])
    nxt = next_run(s, ist(*MON, 9, 0))
    assert nxt == ist(*MON, 13, 0).astimezone(UTC)


def test_next_run_skips_weekend():
    s = step(["08:30"])
    friday_evening = ist(2026, 10, 2, 18, 0)
    assert next_run(s, friday_evening).astimezone(IST) == ist(2026, 10, 5, 8, 30)


def test_next_run_none_when_paused_or_empty():
    assert next_run(step(["08:30"]), ist(*MON, 7, 0), paused=True) is None
    assert next_run(step([]), ist(*MON, 7, 0)) is None


def test_due_within_window():
    s = step(["08:30"])
    assert due_slot(s, ist(*MON, 8, 40), last_started=None) == ist(*MON, 8, 30)


def test_not_due_before_slot():
    assert due_slot(step(["08:30"]), ist(*MON, 8, 20), last_started=None) is None


def test_missed_slot_is_skipped_not_stacked():
    assert due_slot(step(["08:30"]), ist(*MON, 10, 0), last_started=None) is None


def test_not_due_twice_for_same_slot():
    s = step(["08:30"])
    started = ist(*MON, 8, 31)
    assert due_slot(s, ist(*MON, 8, 45), last_started=started) is None


def test_manual_run_before_slot_does_not_block_slot():
    s = step(["08:30"])
    manual = ist(*MON, 8, 0)
    assert due_slot(s, ist(*MON, 8, 35), last_started=manual) == ist(*MON, 8, 30)


def test_paused_never_due():
    assert due_slot(step(["08:30"]), ist(*MON, 8, 35), last_started=None, paused=True) is None


def test_day_toggle_respected():
    s = step(["08:30"], days=["tue"])
    assert due_slot(s, ist(*MON, 8, 35), last_started=None) is None


def test_ist_day_boundary():
    """01:00 IST Monday is 19:30 UTC Sunday; it must count as Monday, not Sunday."""
    s = step(["01:00"], days=["mon"])
    now_utc = datetime(2026, 9, 27, 19, 40, tzinfo=UTC)  # 01:10 IST Monday
    assert due_slot(s, now_utc, last_started=None) == ist(*MON, 1, 0)
    sunday_only = step(["01:00"], days=["sun"])
    assert due_slot(sunday_only, now_utc, last_started=None) is None


def test_slot_just_before_midnight_seen_after_midnight():
    s = step(["23:55"], days=["mon"])
    after_midnight = ist(2026, 9, 29, 0, 5)
    assert due_slot(s, after_midnight, last_started=None) == ist(*MON, 23, 55)


def test_naive_datetime_rejected():
    with pytest.raises(ScheduleError):
        next_run(step(["08:30"]), datetime(2026, 9, 28, 8, 0))


def test_format_ist_labels():
    now = ist(*MON, 9, 0)
    assert format_ist(ist(*MON, 13, 0), now) == "1:00 PM"
    assert format_ist(ist(2026, 9, 29, 8, 30), now) == "8:30 AM tomorrow"
    assert format_ist(ist(2026, 10, 1, 8, 30), now) == "Thu 8:30 AM"


def test_window_is_configurable():
    s = step(["08:30"])
    assert due_slot(s, ist(*MON, 8, 50), last_started=None, window=timedelta(minutes=10)) is None
