"""Daily LLM usage stored in the llm_usage table (survives across runs)."""

from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import LlmUsage


class DbUsage:
    def __init__(self, db: Session, provider: str) -> None:
        self.db, self.provider = db, provider

    def _row(self, day: date) -> LlmUsage | None:
        return self.db.scalar(
            select(LlmUsage).where(LlmUsage.day == day, LlmUsage.provider == self.provider)
        )

    def requests_on(self, day: date) -> int:
        row = self._row(day)
        return row.requests if row else 0

    def record(self, day: date, input_tokens: int, output_tokens: int) -> None:
        row = self._row(day)
        if row is None:
            row = LlmUsage(
                day=day, provider=self.provider, requests=0, input_tokens=0, output_tokens=0
            )
            self.db.add(row)
        row.requests += 1
        row.input_tokens += input_tokens
        row.output_tokens += output_tokens
        self.db.commit()
