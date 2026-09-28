from app.services.dedupe import (
    canonical_url,
    dedupe_key,
    normalize_location,
    normalize_title,
)


def test_tracking_params_removed():
    a = canonical_url("https://boards.greenhouse.io/acme/jobs/123?utm_source=linkedin&gh_src=abc")
    b = canonical_url("https://boards.greenhouse.io/acme/jobs/123")
    assert a == b


def test_meaningful_params_kept_and_sorted():
    url = canonical_url("https://acme.com/careers?b=2&gh_jid=99&a=1&utm_medium=x")
    assert url == "https://acme.com/careers?a=1&b=2&gh_jid=99"


def test_host_case_www_fragment_trailing_slash():
    a = canonical_url("HTTPS://WWW.Jobs.Lever.co/acme/abc-123/#apply")
    b = canonical_url("https://jobs.lever.co/acme/abc-123")
    assert a == b


def test_title_normalization():
    assert normalize_title("Sr. Backend Engg - II (Python)") == "senior backend engineer 2 python"
    assert (
        normalize_title("Senior Backend Engineer II, Python") == "senior backend engineer 2 python"
    )


def test_location_normalization():
    assert normalize_location("Pune, Maharashtra, India") == "pune"
    assert normalize_location("Remote - India") == "remote"
    assert normalize_location("") == "unknown"


def test_reposted_role_same_key():
    k1 = dedupe_key("Mastercard", "Software Engineer II - Backend", "Pune, India")
    k2 = dedupe_key("Mastercard Ltd", "Software Engineer 2 Backend", "Pune")
    assert k1 == k2


def test_different_roles_different_keys():
    k1 = dedupe_key("Mastercard", "Backend Engineer", "Pune")
    k2 = dedupe_key("Mastercard", "Frontend Engineer", "Pune")
    assert k1 != k2
