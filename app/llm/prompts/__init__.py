"""Versioned prompt templates."""

from pathlib import Path

DIR = Path(__file__).parent


def load(name: str) -> str:
    return (DIR / f"{name}.md").read_text(encoding="utf-8")
