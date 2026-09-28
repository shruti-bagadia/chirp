"""Generic form discovery and fill engine, shared by every `apply_mode=auto` platform.

Rather than hardcoding exact field IDs (which drift as platforms change their
markup), this discovers fields by their accessible label and fills what it
recognizes. Anything it can't confidently map stops the submission and reports
the question back — never a guess (CLAUDE.md: "Anything unexpected → Needs a
hand, never a guess").
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from applier.form_mapper import Applicant, closest_option, fit_to_limit, standard_value


class Blocked(RuntimeError):
    """The page shows a captcha, a login wall, or a closed posting."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


class AnswerLookup(Protocol):
    def __call__(self, question: str) -> tuple[str | None, str | None, float | None]:
        """question -> (answer_text, answer_id, match_score), or (None, None, None)."""
        ...


@dataclass(frozen=True, slots=True)
class PlatformConfig:
    name: str
    resume_label_hints: tuple[str, ...] = ("resume", "cv")
    cover_letter_label_hints: tuple[str, ...] = ("cover letter",)
    submit_selector: str = "button[type=submit]"
    confirmation_text_hints: tuple[str, ...] = (
        "application submitted",
        "thank you for applying",
        "thanks for applying",
        "successfully submitted",
    )
    field_label_selector: str = "label"


@dataclass
class DiscoveredField:
    label: str
    kind: str  # text | textarea | select | radio | checkbox | file
    required: bool
    options: list[str] = field(default_factory=list)
    locator: Any = None  # a Playwright Locator


@dataclass
class FillOutcome:
    filled: list[tuple[str, str, str | None, float | None]] = field(default_factory=list)
    unanswered: list[str] = field(default_factory=list)


def detect_blocked(page) -> str | None:
    """Captcha / login wall / closed posting, or None if the page looks like a
    normal application form."""
    try:
        html = page.content().lower()
    except Exception:
        return None
    if "recaptcha" in html or "hcaptcha" in html or "verify you are human" in html:
        return "captcha"
    if page.locator("input[type=password]").count() > 0:
        return "login"
    if any(
        p in html
        for p in (
            "no longer accepting applications",
            "position has been filled",
            "posting has closed",
        )
    ):
        return "expired"
    return None


def _associated_input(page, label):
    for_id = label.get_attribute("for")
    if for_id:
        candidate = page.locator(f"#{for_id}")
        if candidate.count() > 0:
            return candidate.first
    nested = label.locator("input, textarea, select")
    if nested.count() > 0:
        return nested.first
    return None


def _classify(input_el) -> tuple[str, list[str]]:
    tag = input_el.evaluate("el => el.tagName.toLowerCase()")
    if tag == "textarea":
        return "textarea", []
    if tag == "select":
        options = input_el.evaluate(
            "el => Array.from(el.options).map(o => (o.textContent || '').trim()).filter(Boolean)"
        )
        return "select", options
    input_type = (input_el.get_attribute("type") or "text").lower()
    if input_type == "file":
        return "file", []
    if input_type in {"radio", "checkbox"}:
        return input_type, []
    return "text", []


def discover_fields(page, config: PlatformConfig) -> list[DiscoveredField]:
    fields: list[DiscoveredField] = []
    labels = page.locator(config.field_label_selector)
    for i in range(labels.count()):
        label = labels.nth(i)
        text = (label.inner_text() or "").strip()
        if not text:
            continue
        input_el = _associated_input(page, label)
        if input_el is None:
            continue
        kind, options = _classify(input_el)
        required = "*" in text or input_el.get_attribute("required") is not None
        fields.append(
            DiscoveredField(
                label=text, kind=kind, required=required, options=options, locator=input_el
            )
        )
    return fields


def _matches_hint(label: str, hints: tuple[str, ...]) -> bool:
    low = label.lower()
    return any(h in low for h in hints)


def _fill_text(locator, value: str) -> None:
    locator.fill(value)


def fill_form(
    page,
    config: PlatformConfig,
    *,
    applicant: Applicant,
    resume_path: str | None,
    cover_letter: str,
    answer_lookup: AnswerLookup,
) -> FillOutcome:
    """Fills every field it can confidently map. `answer_lookup` resolves a custom
    question against the answer bank (exact + semantic matching lives outside this
    module, so this stays DB/embedding-agnostic and unit-testable without either)."""
    outcome = FillOutcome()
    for f in discover_fields(page, config):
        if f.kind == "file" and _matches_hint(f.label, config.resume_label_hints):
            if resume_path:
                f.locator.set_input_files(resume_path)
            elif f.required:
                outcome.unanswered.append(f.label)
            continue
        if f.kind == "file":
            continue  # an upload field we don't recognize; nothing required to guess

        std = standard_value(f.label, applicant)
        if std is not None:
            _fill_text(f.locator, std)
            outcome.filled.append((f.label, std, None, None))
            continue

        if _matches_hint(f.label, config.cover_letter_label_hints):
            _fill_text(f.locator, cover_letter)
            outcome.filled.append((f.label, cover_letter, None, None))
            continue

        answer, answer_id, score = answer_lookup(f.label)
        if answer is None:
            if f.required:
                outcome.unanswered.append(f.label)
            continue

        if f.kind == "select":
            picked = closest_option(answer, f.options)
            if picked is None:
                outcome.unanswered.append(f.label)
                continue
            f.locator.select_option(label=picked)
            outcome.filled.append((f.label, picked, answer_id, score))
        elif f.kind in {"radio", "checkbox"}:
            f.locator.check()
            outcome.filled.append((f.label, answer, answer_id, score))
        else:
            value = fit_to_limit(answer, None)
            _fill_text(f.locator, value)
            outcome.filled.append((f.label, value, answer_id, score))
    return outcome


def looks_submitted(page, config: PlatformConfig) -> bool:
    """Checks that confirmation text is actually *visible*, not just present
    somewhere in the markup — a hidden confirmation div (shown only after a real
    submit) would otherwise false-positive before anything was submitted."""
    for hint in config.confirmation_text_hints:
        try:
            locator = page.get_by_text(hint, exact=False).first
            if locator.count() > 0 and locator.is_visible():
                return True
        except Exception:
            continue
    return False


def submit_form(page, config: PlatformConfig, *, dry_run: bool) -> None:
    """Per docs/10_test_plan.md G11: dry run fills the form and stops there."""
    if dry_run:
        return
    page.locator(config.submit_selector).first.click()
    page.wait_for_load_state("networkidle", timeout=15000)
