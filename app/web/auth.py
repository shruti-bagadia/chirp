"""Dashboard login: session cookie, login rate limiting, and CSRF checks.

Single-user by design (see CLAUDE.md), so the rate limiter is a small in-memory
counter — there's only ever one person to lock out, and it resets on restart.
"""

from __future__ import annotations

import secrets
import time
from dataclasses import dataclass, field

from fastapi import HTTPException, Request

from app.core.config import get_settings
from app.core.security import tokens_match, verify_password

MAX_ATTEMPTS = 10
WINDOW_SECONDS = 15 * 60


@dataclass
class _RateLimiter:
    attempts: list[float] = field(default_factory=list)

    def blocked(self, now: float) -> bool:
        self.attempts = [t for t in self.attempts if now - t < WINDOW_SECONDS]
        return len(self.attempts) >= MAX_ATTEMPTS

    def record_failure(self, now: float) -> None:
        self.attempts.append(now)

    def reset(self) -> None:
        self.attempts.clear()


_limiter = _RateLimiter()


def new_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def login(request: Request, password: str) -> str | None:
    """Try a password. Returns an error message, or None on success."""
    now = time.time()
    if _limiter.blocked(now):
        return "Too many attempts. Try again in a few minutes."
    if not verify_password(password, get_settings().dashboard_password_hash):
        _limiter.record_failure(now)
        return "Wrong password."
    _limiter.reset()
    request.session["authed"] = True
    request.session["csrf"] = new_csrf_token()
    return None


def logout(request: Request) -> None:
    request.session.clear()


def is_authed(request: Request) -> bool:
    return bool(request.session.get("authed"))


def require_login(request: Request) -> None:
    if not is_authed(request):
        raise HTTPException(status_code=303, headers={"Location": "/login"})


def require_csrf(request: Request) -> None:
    token = request.session.get("csrf", "")
    given = request.headers.get("x-csrf-token", "")
    if not tokens_match(given, token):
        raise HTTPException(status_code=403, detail="Your session expired. Refresh and try again.")


def require_csrf_on_mutation(request: Request) -> None:
    """Router-level dependency: only checks CSRF for state-changing methods, so it can
    sit on a router that also serves plain GET pages without breaking navigation."""
    if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        require_csrf(request)
