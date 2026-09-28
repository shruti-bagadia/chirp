"""Tailoring: prompt, parse into a draft the fabrication check can verify."""

from __future__ import annotations

from app.llm import prompts
from app.llm.base import SchemaError
from app.profile.model import Profile
from app.services.fabrication_check import Bullet, TailorDraft
from app.services.scoring import JobForLLM, truncate_words

PROMPT_VERSION = "tailor_v2"


def parse_draft(d: dict) -> TailorDraft:
    try:
        exp = {
            str(k): [Bullet(str(b["fact_id"]), str(b["text"]).strip()) for b in v]
            for k, v in (d.get("experience") or {}).items()
        }
        draft = TailorDraft(
            summary=str(d["summary"]).strip(),
            summary_fact_ids=[str(x) for x in d.get("summary_fact_ids") or []],
            skills_priority=[str(x) for x in d.get("skills_priority") or []][:12],
            experience=exp,
            change_summary=str(d.get("change_summary", "")).strip()[:200],
            cover_letter=str(d.get("cover_letter", "")).strip(),
        )
    except (KeyError, TypeError, AttributeError) as exc:
        raise SchemaError(f"Bad tailoring output: {exc}") from exc
    if not draft.experience:
        raise SchemaError("experience is empty")
    if any(len(b.text.split()) > 55 for bs in draft.experience.values() for b in bs):
        raise SchemaError("a bullet is over 40 words")
    return draft


def build_prompt(
    job: JobForLLM, profile: Profile, role_focus: str = "", fix_errors: list[str] | None = None
) -> tuple[str, str]:
    system = prompts.load(PROMPT_VERSION)
    user = (
        f"JOB\nTitle: {job.title}\nCompany: {job.company}\nFocus: {role_focus}\n\n"
        f"{truncate_words(job.description, 1500)}\n\nCANDIDATE FACTS\n{profile.prompt_block()}"
    )
    if fix_errors:
        user += "\n\nYOUR PREVIOUS DRAFT BROKE THESE RULES. Fix every one:\n- " + "\n- ".join(
            fix_errors
        )
    return system, user


def fill_company(text: str, company: str) -> str:
    return text.replace("[Company]", company).replace("[COMPANY]", company)
