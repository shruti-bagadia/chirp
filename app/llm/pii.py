"""Strip personal details before any LLM call, and put them back after."""

from __future__ import annotations

import re

_PHONE = re.compile(r"(?:\+?91[\s-]?)?[6-9]\d{4}[\s-]?\d{5}\b")
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")


class Redactor:
    def __init__(self, identity: dict) -> None:
        links = identity.get("links") or {}
        pairs = [
            (identity.get("name"), "[CANDIDATE]"),
            (identity.get("email"), "[EMAIL]"),
            (identity.get("phone"), "[PHONE]"),
            (links.get("linkedin"), "[LINKEDIN]"),
            (links.get("github"), "[GITHUB]"),
        ]
        # Longest first so a full name is replaced before any part of it.
        self.pairs = sorted(((v, p) for v, p in pairs if v), key=lambda x: -len(x[0]))
        name = identity.get("name") or ""
        self.first_name = name.split()[0] if name else None

    def redact(self, text: str) -> str:
        for value, placeholder in self.pairs:
            text = re.sub(re.escape(value), placeholder, text, flags=re.I)
        if self.first_name:
            text = re.sub(rf"\b{re.escape(self.first_name)}\b", "[CANDIDATE]", text)
        text = _EMAIL.sub("[EMAIL]", text)
        text = _PHONE.sub("[PHONE]", text)
        return text

    def restore(self, text: str) -> str:
        for value, placeholder in reversed(self.pairs):
            text = text.replace(placeholder, value)
        return text

    def leaks(self, text: str) -> list[str]:
        """Any profile PII value still present (used by tests and a final guard)."""
        found = [p for v, p in self.pairs if v.lower() in text.lower()]
        if _EMAIL.search(text):
            found.append("[EMAIL]")
        if _PHONE.search(text):
            found.append("[PHONE]")
        return found
