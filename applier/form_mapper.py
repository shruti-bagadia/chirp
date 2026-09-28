"""Pure field-mapping logic for the Applier: given a question the form asks, decide
what to fill in — or that it needs a hand. No Playwright import here on purpose, so
this stays testable without a browser (see tests/unit/test_form_mapper.py).
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Applicant:
    """Everything needed to fill a form's standard (non-custom) fields."""

    first_name: str
    last_name: str
    email: str
    phone: str
    location: str
    linkedin: str = ""
    github: str = ""


def applicant_from_identity(identity: dict) -> Applicant:
    name = (identity.get("name") or "").strip()
    first, _, last = name.partition(" ")
    links = identity.get("links") or {}
    return Applicant(
        first_name=first or name,
        last_name=last,
        email=identity.get("email", ""),
        phone=identity.get("phone", ""),
        location=identity.get("location", ""),
        linkedin=links.get("linkedin", ""),
        github=links.get("github", ""),
    )


_STANDARD_FIELDS: dict[str, str] = {
    "first name": "first_name",
    "given name": "first_name",
    "last name": "last_name",
    "surname": "last_name",
    "family name": "last_name",
    "email": "email",
    "email address": "email",
    "phone": "phone",
    "phone number": "phone",
    "mobile": "phone",
    "mobile number": "phone",
    "location": "location",
    "current location": "location",
    "city": "location",
    "linkedin profile": "linkedin",
    "linkedin url": "linkedin",
    "linkedin": "linkedin",
    "github": "github",
    "github url": "github",
    "github profile": "github",
}


def _normalize_label(label: str) -> str:
    return re.sub(r"\s+", " ", label).strip().lower().rstrip(" *:").strip()


def standard_value(label: str, applicant: Applicant) -> str | None:
    """A value for one of the form's standard identity fields, or None if `label`
    isn't one (in which case it's a custom question — see the answer bank)."""
    attr = _STANDARD_FIELDS.get(_normalize_label(label))
    return getattr(applicant, attr) if attr else None


def fit_to_limit(text: str, limit: int | None, short_answer: str | None = None) -> str:
    """Trim an answer to fit a form's character limit, keeping the core point.

    Prefers a pre-written `short_answer` if it fits; otherwise cuts at the last
    whole word inside the limit (never mid-word), per docs/09_answer_bank.md.
    """
    if limit is None or len(text) <= limit:
        return text
    source = short_answer if short_answer else text
    if len(source) <= limit:
        return source
    cut = source[:limit].rsplit(" ", 1)[0]
    return cut.rstrip(".,;: ") or source[:limit]


_YES_WORDS = {"yes", "y", "true", "authorized", "eligible"}
_NO_WORDS = {"no", "n", "false", "not authorized", "not eligible", "ineligible"}


def closest_option(value: str, options: list[str]) -> str | None:
    """Map a free-form value (or answer) onto the closest dropdown/radio option."""
    if not options:
        return None
    norm_value = value.strip().lower()
    norm_options = [o.strip().lower() for o in options]

    for opt, norm in zip(options, norm_options, strict=True):
        if norm == norm_value:
            return opt
    # Substring either direction: "30" <-> "30 days", "yes, I am" <-> "yes".
    for opt, norm in zip(options, norm_options, strict=True):
        if norm in norm_value or norm_value in norm:
            return opt
    # Common yes/no phrasing a plain substring/similarity check won't catch.
    if any(w in norm_value for w in _NO_WORDS):
        match = next(
            (o for o, n in zip(options, norm_options, strict=True) if n in _NO_WORDS), None
        )
        if match:
            return match
    if any(w in norm_value for w in _YES_WORDS):
        match = next(
            (o for o, n in zip(options, norm_options, strict=True) if n in _YES_WORDS), None
        )
        if match:
            return match
    matches = difflib.get_close_matches(norm_value, norm_options, n=1, cutoff=0.5)
    if matches:
        return options[norm_options.index(matches[0])]
    return None
