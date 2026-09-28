from datetime import UTC, datetime, timedelta

import pytest

from app.services.schedule import ScheduleError
from app.web.demo_store import DEMO_RUN_SECONDS, DemoStore

NOW = datetime(2026, 9, 28, 3, 0, tzinfo=UTC)  # 08:30 IST Monday


def fresh():
    return DemoStore()


def test_pending_sorted_by_score():
    scores = [j.score for j in fresh().pending()]
    assert scores == sorted(scores, reverse=True) and len(scores) == 8


def test_approve_and_reject():
    s = fresh()
    ids = [j.id for j in s.pending()[:3]]
    assert s.decide(ids[:2], "approve") == 2
    assert s.decide(ids[2:], "reject") == 1
    assert len(s.pending()) == 5 and len(s.approved()) == 2


def test_decide_twice_counts_once():
    s = fresh()
    jid = s.pending()[0].id
    assert s.decide([jid], "approve") == 1
    assert s.decide([jid], "approve") == 0


def test_bad_action():
    with pytest.raises(ValueError):
        fresh().decide([1], "maybe")


def test_ctc_override_validated():
    s = fresh()
    assert s.set_ctc(1, 19).ctc == 19
    with pytest.raises(ValueError):
        s.set_ctc(1, 200)


def test_answer_requires_text_and_removes_hand():
    s = fresh()
    with pytest.raises(ValueError):
        s.answer("q1", "   ")
    s.answer("q1", "I over-polish; I now agree on scope first.")
    assert s.get_hand("q1") is None


def test_quick_apply_adds_to_flown():
    s = fresh()
    before = len(s.flown)
    s.mark_applied("k1")
    assert len(s.flown) == before + 1 and s.flown[0].company == "Deutsche Bank"


def test_callback_toggle():
    s = fresh()
    fid = s.flown[0].id
    assert s.toggle_callback(fid).callback is True
    assert s.toggle_callback(fid).callback is False


def test_schedule_edits():
    s = fresh()
    s.add_time("find", "17:00")
    assert "17:00" in s.schedule["find"]["times"]
    s.remove_time("find", "08:30")
    assert "08:30" not in s.schedule["find"]["times"]
    with pytest.raises(ScheduleError):
        s.add_time("find", "25:00")


def test_day_toggle_applies_to_find_and_apply():
    s = fresh()
    s.toggle_day("fri")
    assert "fri" not in s.schedule["find"]["days"] and "fri" not in s.schedule["apply"]["days"]
    s.toggle_day("fri")
    assert s.schedule["find"]["days"][-1] == "fri"


def test_pause_changes_next_label():
    s = fresh()
    assert s.next_label("find", NOW) != "not scheduled"
    s.toggle_pause()
    assert s.next_label("find", NOW) == "not scheduled"


def test_limits_clamped():
    s = fresh()
    for _ in range(30):
        s.step_limit("daily_apply_cap", 1)
    assert s.settings["daily_apply_cap"] == 20
    with pytest.raises(ValueError):
        s.step_limit("nope", 1)


def test_run_lock_one_at_a_time():
    s = fresh()
    assert s.start_run("find", NOW)
    assert not s.start_run("apply", NOW)
    later = NOW + timedelta(seconds=DEMO_RUN_SECONDS + 1)
    assert s.start_run("apply", later)


def test_fly_run_applies_approved_up_to_cap():
    s = fresh()
    s.settings["daily_apply_cap"] = 2
    s.decide([j.id for j in s.pending()[:3]], "approve")
    s.start_run("apply", NOW)
    msgs = s.finish_runs(NOW + timedelta(seconds=DEMO_RUN_SECONDS + 1))
    assert msgs == ["Flew 2 applications."] and len(s.approved()) == 1


def test_find_refills_empty_nest_with_new_ids():
    s = fresh()
    s.decide([j.id for j in s.pending()], "reject")
    s.start_run("find", NOW)
    s.finish_runs(NOW + timedelta(seconds=DEMO_RUN_SECONDS + 1))
    ids = [j.id for j in s.jobs]
    assert len(s.pending()) == 8 and len(ids) == len(set(ids))


def test_flown_detail_has_answers_and_url():
    s = fresh()
    f = s.get_flown(1)
    assert f.url.startswith("https://") and ("Notice period", "15 days") in f.answers
    assert s.get_flown(999) is None


def test_quick_apply_flown_marked_by_you():
    s = fresh()
    s.mark_applied("k1")
    assert s.flown[0].via == "You"
