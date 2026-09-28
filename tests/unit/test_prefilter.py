from datetime import UTC, datetime, timedelta

import pytest

from app.services.prefilter import (
    LocationFit,
    Posting,
    PrefilterConfig,
    classify_location,
    contract_months,
    parse_experience,
    run_prefilter,
)

NOW = datetime(2026, 9, 28, 3, 0, tzinfo=UTC)
CFG = PrefilterConfig()


def check(**kw):
    kw.setdefault("title", "Backend Engineer")
    kw.setdefault("location", "Pune, India (Hybrid)")
    return run_prefilter(Posting(**kw), CFG, NOW)


def test_good_job_passes():
    r = check(description="Python, FastAPI. 2-4 years of experience.")
    assert r.passed and r.location_fit is LocationFit.PUNE_HYBRID and r.experience == (2, 4)


@pytest.mark.parametrize(
    "title",
    [
        "Frontend Engineer",
        "QA Engineer",
        "SDET",
        "Data Analyst",
        "Android Developer",
        "React Developer",
        "Engineering Manager",
        "Principal Engineer",
        "Software Engineer Intern",
    ],
)
def test_excluded_titles(title):
    r = check(title=title)
    assert not r.passed


@pytest.mark.parametrize(
    "title",
    [
        "Python Developer",
        "SDE 2",
        "AI Engineer",
        "LLM Engineer",
        "GenAI Engineer",
        "Software Development Engineer",
        "Solutions Engineer",
        "Backend Developer - APIs",
    ],
)
def test_target_titles_pass(title):
    assert check(title=title).passed


def test_non_target_title():
    assert not check(title="Marketing Associate").passed


def test_staff_title_not_blocked_by_title_alone():
    """ "Staff" isn't excluded by title (unlike "principal") — India-market title
    use is inconsistent, so the precise `parse_experience` years-asked check is
    what should reject overly senior postings, not the word itself."""
    r = check(title="Staff Software Engineer", description="Python, FastAPI. 3+ years experience.")
    assert r.passed


def test_staff_title_still_rejected_when_it_really_does_ask_for_too_much():
    r = check(title="Staff Software Engineer", description="Python, FastAPI. 8+ years experience.")
    assert not r.passed and "8" in r.reason


def test_api_word_boundary():
    assert not check(title="Rapid Response Specialist").passed


def test_java_without_python_filtered_but_with_python_kept():
    assert not check(title="Java Backend Developer", description="Spring Boot").passed
    assert check(title="Java Backend Developer", description="Java and Python services").passed


def test_dotnet_filtered():
    assert not check(title=".NET Backend Developer").passed


def test_blocked_company():
    r = check(company_blocked=True)
    assert not r.passed and r.reason == "Company is blocked"


@pytest.mark.parametrize(
    "text,expected",
    [
        ("3-5 years of experience", (3, 5)),
        ("3 to 5 yrs", (3, 5)),
        ("5+ years", (5, None)),
        ("Minimum 2 years", (2, None)),
        ("at least 3 years", (3, None)),
        ("4 years of backend experience", (4, None)),
        ("No experience mentioned", None),
    ],
)
def test_parse_experience(text, expected):
    assert parse_experience(text) == expected


def test_too_much_experience():
    r = check(description="We need 5+ years of Python.")
    assert not r.passed and "5" in r.reason


@pytest.mark.parametrize(
    "location,description,expected",
    [
        ("Pune, India", "This is a hybrid role", LocationFit.PUNE_HYBRID),
        ("Pune", "Work from office 5 days", LocationFit.PUNE_ONSITE),
        ("Pune", "", LocationFit.PUNE_UNKNOWN),
        ("Remote - India", "", LocationFit.REMOTE_INDIA),
        ("Remote", "", LocationFit.REMOTE_INDIA),
        ("Remote, USA", "", LocationFit.OTHER),
        ("Mumbai (Hybrid)", "", LocationFit.OTHER),
        ("Bengaluru", "", LocationFit.OTHER),
    ],
)
def test_classify_location(location, description, expected):
    assert classify_location(location, description) is expected


def test_pune_onsite_passes_with_flag():
    r = check(location="Pune", description="Onsite role")
    assert r.passed and r.flags == ["onsite"]


def test_mumbai_hybrid_filtered():
    assert not check(location="Mumbai, Hybrid").passed


@pytest.mark.parametrize(
    "text,months",
    [
        ("This is a 3-month contract", 3),
        ("Contract duration: 6 months", 6),
        ("contract for 4 months", 4),
        ("Full-time permanent role", None),
    ],
)
def test_contract_months(text, months):
    assert contract_months(text) == months


def test_short_contract_filtered_long_contract_kept():
    assert not check(description="3 month contract").passed
    assert check(description="Contract duration: 12 months").passed


def test_salary_floor():
    assert not check(salary_max_lpa=12, salary_floor_lpa=15).passed
    assert check(salary_max_lpa=18, salary_floor_lpa=15).passed
    assert check(salary_max_lpa=None, salary_floor_lpa=15).passed


def test_old_posting_filtered():
    assert not check(posted_at=NOW - timedelta(days=10)).passed
    assert check(posted_at=NOW - timedelta(days=2)).passed
