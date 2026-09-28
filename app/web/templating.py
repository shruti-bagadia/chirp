"""Shared Jinja setup: used by the app and by the static preview build."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.services.schedule import IST

TEMPLATE_DIR = Path(__file__).parent / "templates"


def ampm(value: str) -> str:
    """'13:00' -> '1:00 PM'."""
    h, m = (int(x) for x in value.split(":"))
    return f"{h % 12 or 12}:{m:02d} {'PM' if h >= 12 else 'AM'}"


def greeting(now: datetime) -> str:
    hour = now.astimezone(IST).hour
    return "Good morning" if hour < 12 else "Good afternoon" if hour < 17 else "Good evening"


def configure(env: Environment) -> Environment:
    env.filters["ampm"] = ampm
    return env


def make_env() -> Environment:
    return configure(
        Environment(loader=FileSystemLoader(TEMPLATE_DIR), autoescape=select_autoescape(["html"]))
    )
