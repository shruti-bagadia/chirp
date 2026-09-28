"""Playwright browser/context management for the Applier.

A persistent profile directory means logged-in sessions on career portals survive
between runs (per docs/03_architecture.md: "your logged-in browser sessions").
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

DEFAULT_PROFILE_DIR = Path(".chirp/browser-profile")


@contextmanager
def launch_browser(
    *,
    headless: bool = True,
    profile_dir: str | Path = DEFAULT_PROFILE_DIR,
    channel: str | None = "msedge",
) -> Iterator[BrowserContext]:  # noqa: F821 - Playwright type, imported lazily below
    """`channel="msedge"` uses Windows' built-in Edge instead of downloading
    Playwright's own bundled Chromium — handy since that download depends on a
    Microsoft CDN endpoint that isn't always reachable. Pass `channel=None` to use
    the bundled Chromium instead, once `playwright install chromium` succeeds."""
    from playwright.sync_api import sync_playwright

    Path(profile_dir).mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            str(profile_dir), headless=headless, channel=channel
        )
        try:
            yield context
        finally:
            context.close()
