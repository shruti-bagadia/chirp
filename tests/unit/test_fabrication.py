from pathlib import Path

from app.profile.model import Profile
from app.services.fabrication_check import Bullet, TailorDraft, check, numbers_in, tools_in

PROFILE = Profile.load(Path(__file__).resolve().parents[2] / "profile.example" / "facts.yaml")


def draft(**over):
    base = dict(
        summary=(
            "Backend Engineer with 2 years building FastAPI services that cut "
            "reporting from 3 hours to 10 minutes."
        ),
        summary_fact_ids=["acme.reports"],
        skills_priority=["Python", "FastAPI", "Redis"],
        experience={
            "acme": [
                Bullet(
                    "acme.reports",
                    "Built a FastAPI reporting service, cutting generation "
                    "from 3 hours to 10 minutes.",
                ),
                Bullet(
                    "acme.cache", "Added Redis caching and background workers for 4 partner teams."
                ),
            ]
        },
        change_summary="Led with reporting",
        cover_letter=(
            "Dear Globex team, I build Python and FastAPI services. At Acme "
            "Analytics I cut reports from 3 hours to 10 minutes."
        ),
    )
    base.update(over)
    return TailorDraft(**base)


def test_clean_draft_passes():
    r = check(draft(), PROFILE, "Globex")
    assert r.passed, r.failures


def test_numbers_and_tools_extraction():
    assert numbers_in("95%+ and ~12.6k and 2–6 hours, AWS S3, GSTR-3B") == {"95", "12.6", "2", "6"}
    assert tools_in("Python on AWS S3 with Kubernetes") == {"python", "s3", "kubernetes"}


def test_changed_number_blocked():
    d = draft(
        experience={"acme": [Bullet("acme.reports", "Cut generation from 3 hours to 5 minutes.")]}
    )
    assert any("number 5" in f for f in check(d, PROFILE, "Globex").failures)


def test_new_tool_blocked():
    d = draft(
        experience={"acme": [Bullet("acme.cache", "Added Redis and Kafka caching for 4 teams.")]}
    )
    assert any("kafka" in f for f in check(d, PROFILE, "Globex").failures)


def test_tool_from_allowed_skills_is_fine():
    d = draft(
        experience={"acme": [Bullet("acme.cache", "Added Redis caching in Docker for 4 teams.")]}
    )
    assert check(d, PROFILE, "Globex").passed


def test_unknown_fact_and_experience_blocked():
    d = draft(experience={"acme": [Bullet("acme.nope", "Did things.")], "ghost": []})
    fails = check(d, PROFILE, "Globex").failures
    assert any("Unknown fact id acme.nope" in f for f in fails) and any("ghost" in f for f in fails)


def test_duplicate_fact_blocked():
    b = Bullet("acme.cache", "Added Redis caching for 4 teams.")
    assert any(
        "used twice" in f for f in check(draft(experience={"acme": [b, b]}), PROFILE, "X").failures
    )


def test_never_claim_blocked():
    d = draft(summary="Team lead with 2 years of backend work.")
    assert any("never-claim" in f for f in check(d, PROFILE, "Globex").failures)


def test_summary_numbers_must_come_from_cited_facts():
    d = draft(
        summary="Backend Engineer with 2 years; 92% accuracy OCR.",
        summary_fact_ids=["acme.reports"],
    )
    assert any("Summary: number 92" in f for f in check(d, PROFILE, "Globex").failures)


def test_skill_not_allowed():
    assert any(
        "Skill Kubernetes" in f
        for f in check(draft(skills_priority=["Kubernetes"]), PROFILE, "X").failures
    )


def test_cover_letter_checked():
    d = draft(cover_letter="At Acme I used Kubernetes to serve 50 teams.")
    fails = check(d, PROFILE, "Globex").failures
    assert any("Cover letter: mentions kubernetes" in f for f in fails)
    assert any("Cover letter: number 50" in f for f in fails)


def test_other_employer_named_blocked():
    d = draft(cover_letter="I previously worked at Mastercard on payments.")
    assert any("mastercard" in f for f in check(d, PROFILE, "Globex").failures)
    assert check(draft(cover_letter="I'd love to join Mastercard."), PROFILE, "Mastercard").passed


def test_ordinary_english_use_of_ambiguous_tech_words_not_flagged():
    """ "Express", "Go", "Rust", "Spring" double as ordinary English words. Lowercase,
    sentence use shouldn't be mistaken for a claimed tech skill (real bug: a Gemini
    cover letter using "express my interest" got rejected as fabricating Express.js)."""
    assert tools_in("I'd love to express my interest in this role.") == set()
    assert tools_in("I always go the extra mile for my team.") == set()
    assert tools_in("I won't let my skills rust after this project.") == set()
    assert tools_in("I'm ready to spring into action on day one.") == set()


def test_capitalized_ambiguous_tech_words_still_caught():
    assert tools_in("Built the API in Express and deployed it.") == {"express"}
    assert tools_in("Wrote the service in Go for performance.") == {"go"}
    assert tools_in("Migrated the backend to Rust.") == {"rust"}
    assert tools_in("Used Spring to wire up dependency injection.") == {"spring"}
