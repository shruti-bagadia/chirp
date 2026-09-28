import pytest

from app.connectors.detect import detect, from_html, from_url
from app.db.enums import ApplyMode, Platform


@pytest.mark.parametrize(
    "url,platform,board",
    [
        ("https://boards.greenhouse.io/acmepay", Platform.GREENHOUSE, "acmepay"),
        ("https://job-boards.greenhouse.io/acmepay/jobs/123", Platform.GREENHOUSE, "acmepay"),
        (
            "https://boards.greenhouse.io/embed/job_board?for=acmepay",
            Platform.GREENHOUSE,
            "acmepay",
        ),
        ("https://jobs.lever.co/finloop", Platform.LEVER, "finloop"),
        ("jobs.lever.co/finloop/abc-123", Platform.LEVER, "finloop"),
        ("https://jobs.ashbyhq.com/lexa", Platform.ASHBY, "lexa"),
        (
            "https://acme.wd5.myworkdayjobs.com/en-US/External",
            Platform.WORKDAY,
            "acme/wd5/External",
        ),
        (
            "https://acme.wd1.myworkdayjobs.com/Careers/job/Pune/Backend_R123",
            Platform.WORKDAY,
            "acme/wd1/Careers",
        ),
        ("https://careers.smartrecruiters.com/AcmeCorp", Platform.SMARTRECRUITERS, "AcmeCorp"),
        ("https://acme.darwinbox.in/ms/candidate/careers", Platform.DARWINBOX, None),
        ("https://fa-abcd.oraclecloud.com/hcmUI/CandidateExperience", Platform.ORACLE, None),
    ],
)
def test_from_url(url, platform, board):
    d = from_url(url)
    assert d.platform is platform and d.board_id == board


def test_auto_apply_only_for_supported_platforms():
    assert from_url("https://jobs.lever.co/x").apply_mode is ApplyMode.AUTO
    assert (
        from_url("https://acme.wd5.myworkdayjobs.com/External").apply_mode is ApplyMode.QUICK_APPLY
    )


def test_from_html_finds_embedded_boards():
    page = '<script src="https://boards.greenhouse.io/embed/job_board/js?for=acmepay"></script>'
    assert from_html(page).board_id == "acmepay"
    page = '<a href="https://jobs.lever.co/finloop">Open roles</a>'
    assert from_html(page).platform is Platform.LEVER
    page = '<iframe src="https://acme.wd3.myworkdayjobs.com/en-US/Global"></iframe>'
    assert from_html(page).board_id == "acme/wd3/Global"


def test_detect_fallbacks():
    assert detect("https://acme.com/careers").platform is Platform.UNKNOWN
    assert detect("https://acme.com/careers", "<html>no board</html>").platform is Platform.OWN
