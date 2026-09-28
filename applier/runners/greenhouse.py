"""Greenhouse's public application form: plain labeled fields, a resume upload,
and a submit button — the generic engine in `base.py` handles all of it.

Some companies point their careers page at Greenhouse's own hosted board
(job-boards.greenhouse.io/...) directly, where the form is in the top-level
page. Others embed the same form via an iframe on their own branded careers
page instead (confirmed live: Druva's absolute_url renders the form inside
`iframe[src*="job-boards.greenhouse.io/embed/job_app"]`, not in the page
itself) — `embed_iframe_hint` lets the generic engine fall back into that
iframe when the top-level page has no fields."""

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
    embed_iframe_hint="greenhouse.io",
)
