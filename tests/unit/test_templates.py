"""Every page and partial renders with sample data (no web server needed)."""

from datetime import UTC, datetime

from app.web.demo_store import DemoStore
from app.web.templating import ampm, greeting, make_env

NOW = datetime(2026, 9, 28, 3, 0, tzinfo=UTC)


def ctx(store, tab="nest"):
    return {
        "tab": tab,
        "greeting": greeting(NOW),
        "first_name": "Shruti",
        "version": "test",
        "data_mode": "sample data",
        "static": "/static",
        "preview": False,
        "counts": store.counts(),
        "running": None,
        "paused": False,
        "next_find": store.next_label("find", NOW),
        "next_fly": store.next_label("apply", NOW),
        "schedule": store.schedule,
        "tiers": store.settings["ctc_tiers"],
        "limits": store.settings,
    }


def test_ampm_and_greeting():
    assert ampm("13:00") == "1:00 PM" and ampm("00:05") == "12:05 AM"
    assert greeting(NOW) == "Good morning"


def test_nest_page_renders_jobs():
    s = DemoStore()
    html = make_env().get_template("nest.html").render(**ctx(s), jobs=s.pending())
    assert "Mastercard" in html and 'id="queue-form"' in html and "Ready to fly" in html
    assert 'id="perch"' in html and 'id="tpl-sparrow-fly"' in html


def test_empty_nest_state():
    s = DemoStore()
    html = make_env().get_template("nest.html").render(**ctx(s), jobs=[])
    assert "The nest is quiet" in html


def test_other_pages_render():
    s = DemoStore()
    env = make_env()
    assert "New questions" in env.get_template("hands.html").render(
        **ctx(s, "hands"), hands=s.hands
    )
    assert "flown" in env.get_template("flown.html").render(**ctx(s, "flown"), flown=s.flown)
    more = env.get_template("more.html").render(**ctx(s, "more"))
    assert "Chirp is resting" in more and "8:30 AM" in more


def test_partials_render():
    s = DemoStore()
    env = make_env()
    j = s.pending()[0]
    assert j.title in env.get_template("partials/_detail.html").render(j=j)
    assert "Answer once" in env.get_template("partials/_answer.html").render(h=s.get_hand("q1"))
    assert "I've applied" in env.get_template("partials/_quick.html").render(h=s.get_hand("k1"))
    assert "Finding jobs" in env.get_template("partials/_strip.html").render(
        **{**ctx(s), "running": "find"}
    )


def test_user_text_is_escaped():
    s = DemoStore()
    j = s.pending()[0]
    j.title = "<script>alert(1)</script>"
    html = make_env().get_template("partials/_detail.html").render(j=j)
    assert "<script>alert(1)</script>" not in html


def test_flown_detail_renders():
    s = DemoStore()
    html = make_env().get_template("partials/_flown_detail.html").render(f=s.get_flown(1))
    assert "Open application" in html and "Answers submitted" in html and "15 days" in html
