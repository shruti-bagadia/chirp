from app.connectors.gmail_alerts import (
    AlertEmail,
    extract_application,
    extract_ats_links,
    extract_company_names,
)

LINKEDIN_STYLE = """
<html><body>
<p>New job for you: Backend Engineer at Acme Fintech.</p>
<p><a href="https://boards.greenhouse.io/acmefintech/jobs/12345?utm_source=li">
  Backend Engineer at Acme Fintech</a></p>
<p>Also: Python Developer at Bright Labs Pvt Ltd.</p>
<p><a href="https://jobs.lever.co/brightlabs/abcd-1234">View job</a></p>
<p>And: Senior SDE at Some Company Without A Link.</p>
</body></html>
"""

NO_LINKS = """
<html><body>
<p>Recommended for you: AI Engineer at Quantum Systems.</p>
<p>Also hiring: Data Platform Engineer at Riverstone Analytics.</p>
</body></html>
"""


def test_extract_ats_links_finds_known_platforms():
    links = extract_ats_links(LINKEDIN_STYLE)
    assert any("greenhouse.io/acmefintech" in link for link in links)
    assert any("jobs.lever.co/brightlabs" in link for link in links)
    assert len(links) == 2


def test_extract_ats_links_dedupes():
    html = LINKEDIN_STYLE + LINKEDIN_STYLE
    assert len(extract_ats_links(html)) == 2


def test_extract_ats_links_ignores_non_ats_hosts():
    html = '<a href="https://www.linkedin.com/jobs/view/123456">apply</a>'
    assert extract_ats_links(html) == []


def test_extract_company_names_finds_at_company_mentions():
    names = extract_company_names(LINKEDIN_STYLE)
    assert "Acme Fintech" in names
    assert "Bright Labs Pvt Ltd" in names
    assert "Some Company Without A Link" in names


def test_extract_company_names_no_links_needed():
    names = extract_company_names(NO_LINKS)
    assert "Quantum Systems" in names
    assert "Riverstone Analytics" in names


def test_extract_company_names_skips_stopwords_and_long_phrases():
    html = "<p>New job for you: Engineer at the company you follow.</p>"
    names = extract_company_names(html)
    assert not any(n.lower().startswith("the") for n in names)


def test_extract_company_names_dedupes_case_insensitively():
    html = "<p>Role at Acme Corp. Another role at ACME CORP.</p>"
    names = extract_company_names(html)
    assert len([n for n in names if n.lower() == "acme corp"]) == 1


def test_alert_email_dataclass_roundtrip():
    e = AlertEmail(message_id="m1", subject="New jobs", html_body="<p>hi</p>")
    assert e.message_id == "m1" and e.subject == "New jobs" and e.received_at is None


def test_extract_application_finds_title_and_company():
    company, title = extract_application(
        "Application received",
        "<p>Thank you for applying for the Backend Engineer role at Acme Corp.</p>",
    )
    assert company == "Acme Corp"
    assert title == "Backend Engineer"


def test_extract_application_without_role_word():
    company, title = extract_application(
        "You applied",
        "<p>Your application for Backend Engineer at Acme Corp. Thanks for applying!</p>",
    )
    assert company == "Acme Corp"
    assert title == "Backend Engineer"


def test_extract_application_falls_back_to_subject_when_unparsed():
    company, title = extract_application("Application Received - Thank You", "<p>Hi there.</p>")
    assert company == "Unknown company"
    assert title == "Application Received - Thank You"
