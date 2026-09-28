from applier.form_mapper import (
    applicant_from_identity,
    closest_option,
    fit_to_limit,
    standard_value,
)

IDENTITY = {
    "name": "Asha Example",
    "email": "asha@example.com",
    "phone": "+91 90000 00000",
    "location": "Pune, India",
    "links": {"linkedin": "linkedin.com/in/asha-example", "github": "github.com/asha-example"},
}


def test_applicant_from_identity_splits_name():
    a = applicant_from_identity(IDENTITY)
    assert a.first_name == "Asha" and a.last_name == "Example"
    assert a.email == "asha@example.com" and a.linkedin.endswith("asha-example")


def test_standard_value_matches_common_label_variants():
    a = applicant_from_identity(IDENTITY)
    assert standard_value("First Name", a) == "Asha"
    assert standard_value("Email Address *", a) == "asha@example.com"
    assert standard_value("Mobile Number:", a) == "+91 90000 00000"
    assert standard_value("LinkedIn URL", a) == "linkedin.com/in/asha-example"


def test_standard_value_none_for_custom_question():
    a = applicant_from_identity(IDENTITY)
    assert standard_value("What's your greatest weakness?", a) is None


def test_fit_to_limit_prefers_short_answer():
    long_text = (
        "I build backend systems that turn slow manual work into fast APIs, again and again."
    )
    assert fit_to_limit(long_text, 200) == long_text  # fits, unchanged
    trimmed = fit_to_limit(long_text, 20, short_answer="Backend systems builder")
    assert trimmed == "Backend systems" and len(trimmed) <= 20


def test_fit_to_limit_cuts_at_word_boundary_without_short_answer():
    text = "Turning slow manual processes into reliable backend services."
    out = fit_to_limit(text, 20)
    assert len(out) <= 20 and not out.endswith(" ") and " " not in out[-1:]
    assert text.startswith(out.rstrip(".,;: "))


def test_closest_option_exact_and_fuzzy():
    options = ["Immediate", "15 days", "30 days", "60 days"]
    assert closest_option("15 days", options) == "15 days"
    assert closest_option("15 Days", options) == "15 days"
    assert closest_option("30", options) == "30 days"


def test_closest_option_yes_no():
    options = ["Yes", "No"]
    assert closest_option("yes", options) == "Yes"
    assert closest_option("Authorized to work", options) == "Yes"
    assert closest_option("not eligible", options) == "No"


def test_closest_option_no_match_returns_none():
    assert closest_option("purple", ["Yes", "No"]) is None
