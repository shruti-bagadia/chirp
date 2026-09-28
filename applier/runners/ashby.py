"""Ashby's public application form: same shape as Greenhouse/Lever for our
purposes — labeled fields, a resume upload, a submit button."""

from __future__ import annotations

from applier.runners.base import PlatformConfig

CONFIG = PlatformConfig(
    name="ashby",
    resume_label_hints=("resume", "cv", "resume/cv"),
    cover_letter_label_hints=("cover letter",),
    submit_selector="button[type=submit]",
    confirmation_text_hints=(
        "application submitted",
        "thanks for applying",
        "thank you for applying",
        "we've received your application",
    ),
)
