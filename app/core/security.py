"""Password hashing and token checks."""

from __future__ import annotations

import hmac

import bcrypt


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str) -> bool:
    if not password_hash:
        return False
    try:
        return bcrypt.checkpw(password.encode(), password_hash.encode())
    except ValueError:
        return False


def tokens_match(given: str, expected: str) -> bool:
    """Constant-time compare; an empty expected token never matches."""
    return bool(expected) and hmac.compare_digest(given.encode(), expected.encode())
