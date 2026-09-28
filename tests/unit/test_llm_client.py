from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.llm.base import BudgetExhausted, RateLimited, SchemaError
from app.llm.client import LLMClient, parse_json
from app.llm.mock import MockProvider
from app.llm.pii import Redactor
from app.llm.ratelimit import DailyBudget, MemoryUsage, TokenBucket
from app.profile.model import Profile

PROFILE = Profile.load(Path(__file__).resolve().parents[2] / "profile.example" / "facts.yaml")
NOW = datetime(2026, 9, 28, 3, 0, tzinfo=UTC)


class Clock:
    def __init__(self):
        self.t = 0.0
        self.slept = []

    def __call__(self):
        return self.t

    def sleep(self, s):
        self.slept.append(s)
        self.t += s


def make(replies, limit=100, rpm=100):
    clock = Clock()
    usage = MemoryUsage()
    client = LLMClient(
        MockProvider(replies),
        Redactor(PROFILE.identity),
        TokenBucket(rpm, clock=clock, sleep=clock.sleep),
        DailyBudget(limit, usage, now=lambda: NOW),
        sleep=lambda s: None,
        keep_requests=True,
    )
    return client, clock, usage


def ident(d):
    if "ok" not in d:
        raise SchemaError("missing ok")
    return d


def test_parse_json_tolerates_fences_and_chatter():
    assert parse_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert parse_json('Sure! {"a": 2} hope that helps') == {"a": 2}
    with pytest.raises(SchemaError):
        parse_json("no json here")


def test_happy_path_and_usage_recorded():
    client, _, usage = make([{"ok": True}])
    assert client.generate(system="s", user="u", parse=ident) == {"ok": True}
    assert usage.requests_on(NOW.date()) == 1 and client.stats.requests == 1


def test_invalid_json_retried_once():
    client, _, _ = make(["not json", {"ok": 1}])
    assert client.generate(system="s", user="u", parse=ident) == {"ok": 1}
    assert client.stats.retries == 1


def test_invalid_twice_raises():
    client, _, _ = make(["nope", "still nope"])
    with pytest.raises(SchemaError):
        client.generate(system="s", user="u", parse=ident)


def test_rate_limited_backs_off_then_succeeds():
    client, _, _ = make([RateLimited("429"), RateLimited("429"), {"ok": 1}])
    assert client.generate(system="s", user="u", parse=ident) == {"ok": 1}
    assert client.stats.retries == 2


def test_rate_limited_gives_up():
    client, _, _ = make([RateLimited("429")] * 4)
    with pytest.raises(RateLimited):
        client.generate(system="s", user="u", parse=ident)


def test_budget_exhausted_stops_before_calling():
    client, _, _ = make([{"ok": 1}, {"ok": 1}], limit=1)
    client.generate(system="s", user="u", parse=ident)
    with pytest.raises(BudgetExhausted):
        client.generate(system="s", user="u", parse=ident)
    assert len(client.provider.calls) == 1


def test_bucket_paces_requests():
    client, clock, _ = make([{"ok": 1}] * 3, rpm=2)
    for _ in range(3):
        client.generate(system="s", user="u", parse=ident)
    assert clock.slept and sum(clock.slept) >= 29


def test_pii_never_sent_and_restored_in_output():
    client, _, _ = make([{"ok": 1, "letter": "Regards, [CANDIDATE] ([EMAIL])"}])
    user = "Candidate Asha Example, asha@example.com, +91 90000 00000, linkedin.com/in/asha-example"
    out = client.generate(system="s", user=user, parse=ident)
    sent = client.stats.sent[0]
    for secret in ["Asha", "asha@example.com", "90000", "linkedin.com/in/asha-example"]:
        assert secret.lower() not in sent.lower()
    assert "Asha Example" in out["letter"] and "asha@example.com" in out["letter"]


def test_stray_email_or_phone_redacted_too():
    r = Redactor(PROFILE.identity)
    assert "[EMAIL]" in r.redact("mail other.person@corp.com") and "[PHONE]" in r.redact(
        "call 9876543210"
    )


def test_profile_prompt_block_has_no_contact_details():
    block = PROFILE.prompt_block()
    assert "[acme.reports]" in block and "asha@example.com" not in block and "90000" not in block
