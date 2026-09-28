"""Deterministic checks that a tailored resume only says what your facts say."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.connectors.seed import SEED_COMPANIES
from app.profile.model import Profile
from app.services.tech_vocab import ALIASES, TECH_TERMS

_NUMBER = re.compile(r"(?<![A-Za-z0-9.])(\d+(?:\.\d+)?)(?:[kKx](?![A-Za-z])|(?![A-Za-z0-9]|\.\d))")
_EXTRA_COMPANIES = (
    "Google",
    "Microsoft",
    "Meta",
    "Apple",
    "Netflix",
    "Uber",
    "Flipkart",
    "Paytm",
    "Razorpay",
    "PhonePe",
    "Swiggy",
    "Zomato",
    "IBM",
    "Oracle Corporation",
)


def numbers_in(text: str) -> set[str]:
    """Standalone numbers: '95%+' -> 95, '2–6 hours' -> 2, 6, '~12.6k' -> 12.6.

    Skips 'S3', 'GSTR-3B'.
    """
    out = set()
    for m in _NUMBER.finditer(text):
        n = m[1]
        out.add(n.rstrip("0").rstrip(".") if "." in n else n)
    return out


def _norm(term: str) -> str:
    t = term.lower().strip()
    return ALIASES.get(t, t)


# These tech terms double as ordinary English words ("express my interest", "go
# above and beyond", "won't let my skills rust", "spring into action") and show up
# in LLM-written prose (summaries, cover letters) far more than in terse bullet
# text. Case-insensitive matching flagged real cover letters as fabricating a
# tool from a sentence that never meant the tech term at all. Match these ones
# case-sensitively instead — genuine tech mentions are reliably capitalized
# ("Express.js", "Go services"), ordinary use in a sentence usually isn't.
_CASE_SENSITIVE_TERMS = frozenset({"Go", "Rust", "Spring", "Express"})

_TERM_PATTERNS = sorted(
    (
        (
            t,
            re.compile(
                r"(?<![\w+#.])" + re.escape(t) + r"(?![\w+#])",
                re.I if t not in _CASE_SENSITIVE_TERMS else 0,
            ),
        )
        for t in TECH_TERMS
    ),
    key=lambda x: -len(x[0]),
)


def tools_in(text: str) -> set[str]:
    """Tech terms named in text, longest match first so 'AWS S3' isn't also counted as 'S3'."""
    found, masked = set(), text
    for term, pat in _TERM_PATTERNS:
        if pat.search(masked):
            found.add(_norm(term))
            masked = pat.sub(" ", masked)
    return found


@dataclass
class Report:
    failures: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.failures

    def fail(self, msg: str) -> None:
        self.failures.append(msg)


@dataclass
class Bullet:
    fact_id: str
    text: str


@dataclass
class TailorDraft:
    summary: str
    summary_fact_ids: list[str]
    skills_priority: list[str]
    experience: dict[str, list[Bullet]]
    change_summary: str
    cover_letter: str


def _allowed_tools(profile: Profile, fact_tools: list[str]) -> set[str]:
    return {_norm(t) for t in [*fact_tools, *profile.skills_allowed]} | {
        _norm(w)
        for t in [*fact_tools, *profile.skills_allowed]
        for w in re.split(r"[\s/,()&]+", t)
        if w
    }


def check(draft: TailorDraft, profile: Profile, target_company: str) -> Report:
    r = Report()
    all_numbers = set().union(
        *(numbers_in(" ".join(f.numbers) + " " + f.text) for f in profile.all_facts())
    )
    known_companies = {c["name"].lower() for c in SEED_COMPANIES} | {
        c.lower() for c in _EXTRA_COMPANIES
    }
    profile_text = " ".join([*profile.companies(), *(f.text for f in profile.all_facts())]).lower()
    ok_companies = {c for c in known_companies if c in profile_text} | {target_company.lower()}

    def text_checks(
        label: str, text: str, allowed_numbers: set[str], allowed_tools: set[str]
    ) -> None:
        for n in sorted(numbers_in(text) - allowed_numbers):
            r.fail(f"{label}: number {n} isn't in your facts")
        for t in sorted(tools_in(text) - allowed_tools):
            r.fail(f"{label}: mentions {t}, which isn't in your facts")
        low = text.lower()
        for phrase in profile.never_claim:
            if phrase in low:
                r.fail(f'{label}: says "{phrase}", which is on your never-claim list')
        for company in known_companies - ok_companies:
            if re.search(r"\b" + re.escape(company) + r"\b", low):
                r.fail(f"{label}: names {company}, which isn't one of your employers")

    seen_ids: set[str] = set()
    for exp_id, bullets in draft.experience.items():
        exp = profile.experience_by_id(exp_id)
        if exp is None:
            r.fail(f"Unknown experience id {exp_id}")
            continue
        exp_fact_ids = {f.id for f in exp.facts}
        for b in bullets:
            fact = profile.fact(b.fact_id)
            if fact is None or b.fact_id not in exp_fact_ids:
                r.fail(f"Unknown fact id {b.fact_id} under {exp_id}")
                continue
            if b.fact_id in seen_ids:
                r.fail(f"Fact {b.fact_id} used twice")
            seen_ids.add(b.fact_id)
            allowed_n = numbers_in(" ".join(fact.numbers) + " " + fact.text)
            text_checks(f"[{b.fact_id}]", b.text, allowed_n, _allowed_tools(profile, fact.tools))

    for fid in draft.summary_fact_ids:
        if profile.fact(fid) is None:
            r.fail(f"Summary cites unknown fact {fid}")
    summary_facts = [f for f in (profile.fact(i) for i in draft.summary_fact_ids) if f]
    summary_numbers = set().union(
        set(), *(numbers_in(" ".join(f.numbers) + " " + f.text) for f in summary_facts)
    )
    summary_numbers |= numbers_in(str(profile.identity.get("years", "")))
    text_checks("Summary", draft.summary, summary_numbers, _allowed_tools(profile, []))

    allowed_skills = {_norm(s) for s in profile.skills_allowed}
    for s in draft.skills_priority:
        if _norm(s) not in allowed_skills:
            r.fail(f"Skill {s} isn't in your allowed skills")

    letter_numbers = all_numbers | numbers_in(str(profile.identity.get("years", "")))
    text_checks("Cover letter", draft.cover_letter, letter_numbers, _allowed_tools(profile, []))
    return r
