import shutil
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.llm.base import BudgetExhausted
from app.llm.client import LLMClient
from app.llm.mock import MockProvider
from app.llm.pii import Redactor
from app.llm.ratelimit import DailyBudget, MemoryUsage, TokenBucket
from app.profile.model import Profile
from app.resume.render import (
    count_pages,
    emphasize,
    fit_one_page,
    latex_escape,
    render_tex,
)
from app.services.ctc import DEFAULT_BANDS, Tier
from app.services.processor import process_job
from app.services.scoring import JobForLLM, ScoreResult, adjusted_score
from app.services.states import JobStatus
from app.services.tailoring import parse_draft

PROFILE = Profile.load(Path(__file__).resolve().parents[2] / "profile.example" / "facts.yaml")
NOW = datetime(2026, 9, 28, 3, 0, tzinfo=UTC)
JOB = JobForLLM(
    "Backend Engineer", "Globex", "Pune", "hybrid", "Python, FastAPI, Redis. 2-4 years."
)

SCORE = {
    "score": 80,
    "must_haves_matched": ["Python", "FastAPI"],
    "gaps": ["Kafka"],
    "seniority_fit": "match",
    "summary": "Strong backend match",
    "role_focus": "Backend APIs",
}
TAILOR = {
    "summary": (
        "Backend Engineer with 2 years building FastAPI services that cut "
        "reporting from 3 hours to 10 minutes."
    ),
    "summary_fact_ids": ["acme.reports"],
    "skills_priority": ["FastAPI", "Redis", "Python"],
    "experience": {
        "acme": [
            {
                "fact_id": "acme.reports",
                "text": (
                    "Built a FastAPI reporting service that cut generation "
                    "from 3 hours to 10 minutes."
                ),
            },
            {
                "fact_id": "acme.cache",
                "text": "Added Redis caching and background workers, serving 4 partner teams.",
            },
            {
                "fact_id": "acme.lead",
                "text": "Own backend services end to end, from requirements through release.",
            },
        ]
    },
    "change_summary": "Led with the reporting service",
    "cover_letter": (
        "Dear [Company] team, I build Python and FastAPI services. At Acme "
        "Analytics I cut reports from 3 hours to 10 minutes."
    ),
}
FABRICATED = {
    **TAILOR,
    "experience": {
        "acme": [
            {
                "fact_id": "acme.reports",
                "text": "Built a Kafka reporting service cutting generation to 1 minute.",
            },
            {"fact_id": "acme.cache", "text": "Added Redis caching for 4 partner teams."},
        ]
    },
}


def one_page(tex):
    return b"%PDF /Type /Page /Type /Pages"


def two_pages(tex):
    return b"/Type /Page /Type /Page"


def client_with(*replies, limit=100):
    return LLMClient(
        MockProvider(list(replies)),
        Redactor(PROFILE.identity),
        TokenBucket(1000),
        DailyBudget(limit, MemoryUsage(), now=lambda: NOW),
        sleep=lambda s: None,
    )


def run(client, compile_fn=one_page, salary=(None, None), tier=Tier.STANDARD):
    return process_job(
        JOB,
        profile=PROFILE,
        client=client,
        band=DEFAULT_BANDS[tier],
        salary=salary,
        compile_fn=compile_fn,
    )


def test_strong_fit_reaches_the_nest():
    r = run(client_with(SCORE, TAILOR))
    assert r.status is JobStatus.PENDING_REVIEW
    assert r.final_score == 85  # +5 hybrid
    assert r.expected_ctc == 16 and r.ctc_range == "15–17 LPA"
    assert "Globex team" in r.cover_letter and "[Company]" not in r.cover_letter


def test_weak_fit_filtered_without_tailoring():
    c = client_with({**SCORE, "score": 50})
    r = run(c)
    assert r.status is JobStatus.FILTERED_OUT and "below 70" in r.reason
    assert len(c.provider.calls) == 1


def test_fabrication_retry_then_pass():
    c = client_with(SCORE, FABRICATED, TAILOR)
    r = run(c)
    assert r.status is JobStatus.PENDING_REVIEW
    assert "BROKE THESE RULES" in c.provider.calls[2][1]


def test_fabrication_twice_is_error_and_no_pdf():
    r = run(client_with(SCORE, FABRICATED, FABRICATED))
    assert r.status is JobStatus.ERROR and r.resume is None and r.fabrication_failures


def test_invalid_score_json_twice_is_error():
    r = run(client_with("garbage", "more garbage"))
    assert r.status is JobStatus.ERROR and "Scoring failed" in r.reason


def test_budget_exhausted_propagates():
    with pytest.raises(BudgetExhausted):
        run(client_with(SCORE, TAILOR, limit=1))


def test_salary_below_floor_skips_llm():
    c = client_with()
    r = run(c, salary=(8, 12))
    assert r.status is JobStatus.FILTERED_OUT and not c.provider.calls


def test_low_pay_flagged():
    r = run(client_with(SCORE, TAILOR), salary=(12, 16), tier=Tier.PREMIUM)
    assert "low_pay" in r.flags and r.expected_ctc == 16


def test_too_long_resume_trimmed_or_error():
    calls = {"n": 0}

    def shrinking(tex):
        calls["n"] += 1
        return two_pages(tex) if calls["n"] == 1 else one_page(tex)

    r = run(client_with(SCORE, TAILOR), compile_fn=shrinking)
    assert r.status is JobStatus.PENDING_REVIEW and len(r.resume.dropped) == 1
    r2 = run(client_with(SCORE, TAILOR), compile_fn=two_pages)
    assert r2.status is JobStatus.ERROR and "one page" in r2.reason


def test_score_parsing_and_adjustments():
    s = ScoreResult.from_dict(SCORE)
    assert adjusted_score(s, "hybrid") == 85 and adjusted_score(s, "onsite") == 75
    assert adjusted_score(ScoreResult.from_dict({**SCORE, "score": 98}), "hybrid") == 100


def test_tailor_parse_rejects_bad_shapes():
    from app.llm.base import SchemaError

    for bad in [
        {},
        {**TAILOR, "experience": {}},
        {**TAILOR, "experience": {"acme": [{"fact_id": "x", "text": "word " * 60}]}},
    ]:
        with pytest.raises(SchemaError):
            parse_draft(bad)


def test_latex_escaping_and_emphasis():
    assert latex_escape("R&D 95% #1 $5 a_b ~x") == r"R\&D 95\% \#1 \$5 a\_b \textasciitilde{}x"
    assert emphasize("hit 95%+ accuracy", ["95%+"]) == r"hit \textbf{95\%+} accuracy"


def test_render_tex_groups_and_escapes_company():
    d = parse_draft(TAILOR)
    tex = render_tex(PROFILE, d, "AT&T")
    assert (
        r"\groupLabel{Client -- Example Bank}" in tex
        or r"\groupLabel{Client – Example Bank}" in tex
    )
    assert r"\textbf{Reporting Service}" in tex and r"\textbf{3 hours}" in tex
    assert "Asha Example" in tex and r"\begin{document}" in tex


def test_count_pages():
    assert count_pages(b"/Type /Pages /Type /Page /Type/Page") == 2


@pytest.mark.skipif(not (shutil.which("pdflatex") or shutil.which("tectonic")), reason="no LaTeX")
def test_real_pdf_compiles_to_one_page():
    fitted = fit_one_page(PROFILE, parse_draft(TAILOR), "Globex & Co")
    assert fitted.pdf.startswith(b"%PDF") and count_pages(fitted.pdf) == 1
