import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from app.connectors import ashby, greenhouse, lever, workday
from app.connectors.base import ConnectorError, html_to_text, inr_to_lpa, salary_from_text
from app.connectors.registry import connector_for

FIX = Path(__file__).resolve().parents[1] / "fixtures"


def load(name):
    return json.loads((FIX / name).read_text())


class FakeFetcher:
    def __init__(self, payload):
        self.payload, self.calls = payload, []

    def get_json(self, url, params=None):
        self.calls.append((url, params))
        return self.payload

    def post_json(self, url, json_body):
        self.calls.append((url, json_body))
        return self.payload


def test_html_to_text_unescapes_and_keeps_structure():
    text = html_to_text(
        "&lt;p&gt;Hi &amp; welcome&lt;/p&gt;"
        "&lt;ul&gt;&lt;li&gt;One&lt;/li&gt;&lt;li&gt;Two&lt;/li&gt;&lt;/ul&gt;"
    )
    assert "Hi & welcome" in text and "• One" in text and "• Two" in text and "<" not in text


def test_salary_helpers():
    assert inr_to_lpa(1_500_000) == 15.0
    assert inr_to_lpa(125_000, "per-month-salary") == 15.0
    assert salary_from_text("CTC: ₹18-24 LPA") == (18.0, 24.0)
    assert salary_from_text("Competitive pay") == (None, None)


def test_greenhouse_parse():
    jobs = greenhouse.parse(load("greenhouse_jobs.json"))
    assert len(jobs) == 4
    j = jobs[0]
    assert j.external_id == "4012345" and j.title == "Backend Engineer II (Python)"
    assert j.location.startswith("Pune") and "FastAPI" in j.description
    assert (j.salary_min_lpa, j.salary_max_lpa) == (18.0, 24.0)
    assert j.posted_at.year == 2026


def test_greenhouse_fetch_uses_board_api():
    f = FakeFetcher(load("greenhouse_jobs.json"))
    connector_for("greenhouse").fetch("acmepay", f)
    url, params = f.calls[0]
    assert url.endswith("/boards/acmepay/jobs") and params == {"content": "true"}


def test_lever_parse():
    jobs = lever.parse(load("lever_postings.json"))
    assert len(jobs) == 3
    j = jobs[0]
    assert j.workplace == "hybrid" and j.employment == "Full-time"
    assert (j.salary_min_lpa, j.salary_max_lpa) == (15.0, 20.0)
    assert "Design REST APIs" in j.description
    assert j.posted_at.tzinfo is not None


def test_ashby_parse_skips_unlisted():
    jobs = ashby.parse(load("ashby_board.json"))
    assert [j.title for j in jobs] == ["LLM Engineer"]
    assert jobs[0].workplace == "hybrid"


def test_unknown_platform_has_no_connector():
    assert connector_for("icims") is None


class PagedFakeFetcher(FakeFetcher):
    """Serves Workday pages in order, one per POST."""

    def __init__(self, pages):
        super().__init__(None)
        self.pages = list(pages)

    def post_json(self, url, json_body):
        self.calls.append((url, dict(json_body)))
        return self.pages.pop(0) if self.pages else {"total": 0, "jobPostings": []}


def test_workday_board_id_parsing_builds_post_url():
    assert workday.parse_board_id("mastercard/wd1/CorporateCareers") == (
        "mastercard",
        "wd1",
        "CorporateCareers",
    )
    assert (
        workday.api_url("mastercard/wd1/CorporateCareers")
        == "https://mastercard.wd1.myworkdayjobs.com/wday/cxs/mastercard/CorporateCareers/jobs"
    )
    for bad in ["mastercard", "mastercard/CorporateCareers", "a/b/c", ""]:
        with pytest.raises(ConnectorError):
            workday.parse_board_id(bad)


def test_workday_single_page_under_limit():
    page = load("workday_jobs.json")["pages"][1]  # 5 jobs, fewer than the page size
    f = PagedFakeFetcher([page])
    jobs = connector_for("workday").fetch("acme/wd5/External", f)
    assert len(jobs) == 5 and len(f.calls) == 1
    url, body = f.calls[0]
    assert url == "https://acme.wd5.myworkdayjobs.com/wday/cxs/acme/External/jobs"
    assert body == {"appliedFacets": {}, "limit": 20, "offset": 0, "searchText": "India"}
    first = jobs[0]
    assert first.external_id == "R-300120"  # jobReqId wins when present
    assert first.url.startswith("https://acme.wd5.myworkdayjobs.com/External/job/")
    assert first.description == ""
    # no locationsText: falls back to the location in bulletFields
    london = next(j for j in jobs if j.external_id.endswith("R-300122"))
    assert london.location == "London, United Kingdom"


def test_workday_paginates_until_short_page():
    pages = load("workday_jobs.json")["pages"]
    f = PagedFakeFetcher(pages + [{"total": 0, "jobPostings": [{"title": "never read"}]}])
    jobs = connector_for("workday").fetch("mastercard/wd1/CorporateCareers", f)
    assert len(jobs) == 25
    assert [body["offset"] for _, body in f.calls] == [0, 20]
    j = jobs[0]
    assert j.external_id == "Senior-Software-Engineer--Python-_R-300100"
    assert j.url == (
        "https://mastercard.wd1.myworkdayjobs.com/CorporateCareers"
        "/job/Pune-India/Senior-Software-Engineer--Python-_R-300100"
    )
    assert j.location == "Pune, India" and j.posted_at.tzinfo is not None
    assert jobs[1].workplace == "hybrid"
    assert sum("Pune" in x.location for x in jobs) and any("Pune" not in x.location for x in jobs)


def test_workday_stops_at_max_pages():
    full = {"total": 10_000, "jobPostings": [{"title": "x", "externalPath": "/job/x"}] * 20}
    f = PagedFakeFetcher([full] * 100)
    jobs = connector_for("workday").fetch("acme/wd1/Site", f)
    assert len(f.calls) == workday.MAX_PAGES and len(jobs) == 20 * workday.MAX_PAGES


def test_workday_relative_dates():
    now = datetime(2026, 9, 28, 12, tzinfo=UTC)
    assert workday.posted_at_from_text("Posted Today", now) == now
    assert workday.posted_at_from_text("Posted Yesterday", now) == now - timedelta(days=1)
    assert workday.posted_at_from_text("Posted 3 Days Ago", now) == now - timedelta(days=3)
    assert workday.posted_at_from_text("Posted 30+ Days Ago", now) == now - timedelta(days=30)
    assert workday.posted_at_from_text("", now) is None
    assert workday.posted_at_from_text("Posted sometime", now) is None


def test_workday_search_text_is_configurable_and_defaults_empty():
    """The registry sets `search_text="India"` (see registry.py's comment on why),
    but the class itself defaults to unfiltered, and any instance can be built with
    its own term."""
    f = PagedFakeFetcher([{"total": 0, "jobPostings": []}])
    workday.WorkdayConnector().fetch("acme/wd1/Site", f)
    assert f.calls[0][1]["searchText"] == ""

    f2 = PagedFakeFetcher([{"total": 0, "jobPostings": []}])
    workday.WorkdayConnector(search_text="Pune").fetch("acme/wd1/Site", f2)
    assert f2.calls[0][1]["searchText"] == "Pune"
