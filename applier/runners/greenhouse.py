"""Greenhouse's public application form: plain labeled fields, a resume upload,
and a submit button — the generic engine in `base.py` handles all of it."""

from __future__ import annotations

from applier.runners.base import PlatformConfig

CONFIG = PlatformConfig(
    name="greenhouse",
    resume_label_hints=("resume", "cv", "curriculum vitae"),
    cover_letter_label_hints=("cover letter",),
    submit_selector="#submit_app, button[type=submit]",
    confirmation_text_hints=(
        "application submitted",
        "thanks for applying",
        "thank you for applying",
    ),
)
