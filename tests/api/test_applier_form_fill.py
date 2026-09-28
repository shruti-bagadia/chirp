"""Applier form-fill engine against a real (headless) browser.

Uses `page.set_content(...)` instead of a live site, so this never touches a real
company's careers page and needs no network — see docs/10_test_plan.md's FakeATS
approach, minus even needing a server for this particular piece.
"""

from __future__ import annotations

import importlib.util

import pytest

from applier.form_mapper import applicant_from_identity
from applier.runners import ashby, greenhouse
from applier.runners.base import detect_blocked, fill_form, looks_submitted, submit_form

HAS_PLAYWRIGHT = importlib.util.find_spec("playwright") is not None


def _browser_available() -> bool:
    if not HAS_PLAYWRIGHT:
        return False
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            b = p.chromium.launch(channel="msedge", headless=True)
            b.close()
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _browser_available(), reason="no usable browser")

IDENTITY = {
    "name": "Asha Example",
    "email": "asha@example.com",
    "phone": "+91 90000 00000",
    "location": "Pune, India",
    "links": {"linkedin": "linkedin.com/in/asha-example"},
}

FORM_HTML = """
<!DOCTYPE html>
<html><body>
<form id="application_form">
  <label for="first_name">First Name *</label><input id="first_name" required>
  <label for="last_name">Last Name *</label><input id="last_name" required>
  <label for="email">Email *</label><input id="email" type="email" required>
  <label for="phone">Phone</label><input id="phone">
  <label for="resume">Resume/CV *</label><input id="resume" type="file" required>
  <label for="cover_letter">Cover Letter</label><textarea id="cover_letter"></textarea>
  <label for="q_weakness">What is your greatest weakness? *</label>
  <textarea id="q_weakness" required></textarea>
  <label for="q_notice">Notice period *</label>
  <select id="q_notice" required>
    <option>Immediate</option><option>15 days</option><option>30 days</option>
  </select>
  <button type="submit" id="submit_app">Submit application</button>
</form>
<div id="confirmation" hidden>Thanks for applying!</div>
<script>
document.getElementById('application_form').addEventListener('submit', function (e) {
  e.preventDefault();
  document.getElementById('application_form').hidden = true;
  document.getElementById('confirmation').hidden = false;
});
</script>
</body></html>
"""


@pytest.fixture
def page(tmp_path):
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        pg = browser.new_page()
        pg.set_content(FORM_HTML)
        yield pg
        browser.close()


@pytest.fixture
def resume_file(tmp_path):
    path = tmp_path / "resume.pdf"
    path.write_bytes(b"%PDF-1.4 fake resume content")
    return str(path)


def _lookup(answers: dict):
    def fn(question: str):
        for q, a in answers.items():
            if q.lower() in question.lower():
                return a, "answer-id", 0.9
        return None, None, None

    return fn


def test_fills_standard_and_custom_fields(page, resume_file):
    applicant = applicant_from_identity(IDENTITY)
    answers = {
        "greatest weakness": "I over-polish details before shipping.",
        "notice period": "15 days",
    }
    outcome = fill_form(
        page,
        greenhouse.CONFIG,
        applicant=applicant,
        resume_path=resume_file,
        cover_letter="Dear team, I'd love to join.",
        answer_lookup=_lookup(answers),
    )
    assert not outcome.unanswered
    assert page.locator("#first_name").input_value() == "Asha"
    assert page.locator("#email").input_value() == "asha@example.com"
    assert page.locator("#cover_letter").input_value() == "Dear team, I'd love to join."
    assert "over-polish" in page.locator("#q_weakness").input_value()
    assert page.locator("#q_notice").input_value() == "15 days"


def test_required_custom_question_without_a_match_is_unanswered(page, resume_file):
    applicant = applicant_from_identity(IDENTITY)
    outcome = fill_form(
        page,
        greenhouse.CONFIG,
        applicant=applicant,
        resume_path=resume_file,
        cover_letter="",
        answer_lookup=_lookup({}),  # no answers at all
    )
    assert any("weakness" in q.lower() for q in outcome.unanswered)


def test_submit_and_confirmation_detected(page, resume_file):
    applicant = applicant_from_identity(IDENTITY)
    fill_form(
        page,
        greenhouse.CONFIG,
        applicant=applicant,
        resume_path=resume_file,
        cover_letter="Dear team.",
        answer_lookup=_lookup({"weakness": "Detail-oriented to a fault.", "notice": "15 days"}),
    )
    assert not looks_submitted(page, greenhouse.CONFIG)
    submit_form(page, greenhouse.CONFIG, dry_run=False)
    assert looks_submitted(page, greenhouse.CONFIG)


def test_dry_run_does_not_submit(page, resume_file):
    submit_form(page, greenhouse.CONFIG, dry_run=True)
    assert not looks_submitted(page, greenhouse.CONFIG)
    assert page.locator("#application_form").is_visible()


def test_detect_blocked_recognizes_login_wall(page):
    page.set_content("<form><input type='password'></form>")
    assert detect_blocked(page) == "login"


def test_detect_blocked_recognizes_captcha():
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        pg = browser.new_page()
        pg.set_content("<div>Please verify you are human</div>")
        assert detect_blocked(pg) == "captcha"
        browser.close()


def test_detect_blocked_none_for_normal_form(page):
    assert detect_blocked(page) is None


def test_ashby_config_fills_and_submits(page, resume_file):
    """Ashby uses the same generic label-discovery engine as Greenhouse/Lever —
    this confirms its `PlatformConfig` (different hint words, same selectors)
    works end to end, not just that the shared engine does."""
    applicant = applicant_from_identity(IDENTITY)
    outcome = fill_form(
        page,
        ashby.CONFIG,
        applicant=applicant,
        resume_path=resume_file,
        cover_letter="Dear team, excited to apply.",
        answer_lookup=_lookup({"weakness": "I over-polish.", "notice": "15 days"}),
    )
    assert not outcome.unanswered
    assert page.locator("#email").input_value() == "asha@example.com"
    submit_form(page, ashby.CONFIG, dry_run=False)
    assert looks_submitted(page, ashby.CONFIG)
