"""Dispatches the Finder GitHub Actions workflow for "Find now".

Only used once actually deployed (dashboard on Render, Finder on GitHub Actions per
docs/03_architecture.md) — `GITHUB_DISPATCH_TOKEN`/`GITHUB_REPO` are unset for local
dev, so `is_configured()` lets callers fall back to running the Finder in-process.
"""

from __future__ import annotations

import httpx

from app.core.config import Settings

API = "https://api.github.com/repos/{repo}/actions/workflows/{workflow}/dispatches"


class DispatchError(RuntimeError):
    pass


def is_configured(settings: Settings) -> bool:
    return bool(settings.github_repo and settings.github_dispatch_token.get_secret_value())


def dispatch_find(settings: Settings, *, ref: str = "main", workflow: str = "find.yml") -> None:
    if not is_configured(settings):
        raise DispatchError("GITHUB_DISPATCH_TOKEN/GITHUB_REPO aren't set.")
    url = API.format(repo=settings.github_repo, workflow=workflow)
    r = httpx.post(
        url,
        json={"ref": ref},
        headers={
            "Authorization": f"Bearer {settings.github_dispatch_token.get_secret_value()}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        timeout=15,
    )
    if r.status_code != 204:
        raise DispatchError(f"GitHub dispatch failed: {r.status_code} {r.text}")
