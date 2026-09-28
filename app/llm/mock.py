"""Deterministic provider for tests and offline demos."""

from __future__ import annotations

import json
import re
from collections.abc import Callable

from app.llm.base import LLMResponse, RateLimited

Reply = str | dict | Exception | Callable[[str, str], str | dict]

_EXP_HEADER_RE = re.compile(r"^## ([\w.-]+):", re.MULTILINE)
_FACT_RE = re.compile(r"^- \[([\w.-]+)\] (.+)$", re.MULTILINE)


def _first_experience_facts(user: str) -> tuple[str | None, list[tuple[str, str]]]:
    headers = list(_EXP_HEADER_RE.finditer(user))
    if not headers:
        return None, []
    start = headers[0].end()
    end = headers[1].start() if len(headers) > 1 else len(user)
    facts = []
    for m in _FACT_RE.finditer(user[start:end]):
        fact_id, rest = m.group(1), m.group(2)
        text = re.sub(r"\s{2}\([^)]*\)\s*$", "", rest).strip()
        facts.append((fact_id, text))
    return headers[0].group(1), facts


def smart_default(system: str, user: str) -> dict:
    """A safe, generic default reply for `chirp find`/`chirp process` runs without a
    real LLM key: never invents anything, since it only ever echoes facts straight
    back out of whichever real `profile/facts.yaml` produced this prompt.
    """
    if "evaluate how well a candidate fits" in system:
        return {
            "score": 82,
            "must_haves_matched": [],
            "gaps": [],
            "seniority_fit": "match",
            "summary": "Mock score (no LLM key set) — not a real fit assessment.",
            "role_focus": "Backend and AI systems",
        }
    exp_id, facts = _first_experience_facts(user)
    if not exp_id or not facts:
        return {"summary": "", "summary_fact_ids": [], "experience": {}}
    bullets = facts[:3]
    lead_id, lead_text = bullets[0]
    return {
        "summary": f"Backend and AI engineer. {lead_text}"[:280],
        "summary_fact_ids": [lead_id],
        "skills_priority": [],
        "experience": {exp_id: [{"fact_id": fid, "text": text} for fid, text in bullets]},
        "change_summary": "Mock tailoring (no LLM key set): facts kept exactly as written.",
        "cover_letter": (
            f"Dear [Company] team, {lead_text} I'd love to bring that experience to this role."
        )[:900],
    }


class MockProvider:
    name = "mock"

    def __init__(self, replies: list[Reply] | None = None, default: Reply | None = None) -> None:
        self.replies = list(replies or [])
        self.default = default
        self.calls: list[tuple[str, str]] = []

    def generate(
        self, *, system: str, user: str, max_output_tokens: int, temperature: float
    ) -> LLMResponse:
        self.calls.append((system, user))
        reply = self.replies.pop(0) if self.replies else self.default
        if reply is None:
            raise AssertionError("MockProvider ran out of replies")
        if callable(reply) and not isinstance(reply, Exception):
            reply = reply(system, user)
        if isinstance(reply, Exception):
            raise reply
        text = reply if isinstance(reply, str) else json.dumps(reply)
        return LLMResponse(text=text, input_tokens=len(user) // 4, output_tokens=len(text) // 4)


def rate_limited() -> RateLimited:
    return RateLimited("429 from mock")
