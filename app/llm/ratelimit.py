"""Requests-per-minute bucket and daily budget, both with injectable clocks for tests."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from datetime import UTC, date, datetime
from typing import Protocol

from app.llm.base import BudgetExhausted
from app.services.schedule import IST


class TokenBucket:
    def __init__(
        self,
        per_minute: int,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.capacity = max(1, per_minute)
        self.rate = self.capacity / 60.0
        self.tokens = float(self.capacity)
        self.clock, self.sleep = clock, sleep
        self.last = clock()
        self._lock = threading.Lock()

    def acquire(self) -> float:
        """Block until a request may go. Returns seconds waited."""
        waited = 0.0
        with self._lock:
            while True:
                now = self.clock()
                self.tokens = min(self.capacity, self.tokens + (now - self.last) * self.rate)
                self.last = now
                if self.tokens >= 1:
                    self.tokens -= 1
                    return waited
                need = (1 - self.tokens) / self.rate
                self.sleep(need)
                waited += need


class UsageStore(Protocol):
    def requests_on(self, day: date) -> int: ...
    def record(self, day: date, input_tokens: int, output_tokens: int) -> None: ...


class MemoryUsage:
    def __init__(self) -> None:
        self.days: dict[date, list[int]] = {}

    def requests_on(self, day: date) -> int:
        return self.days.get(day, [0, 0, 0])[0]

    def record(self, day: date, input_tokens: int, output_tokens: int) -> None:
        row = self.days.setdefault(day, [0, 0, 0])
        row[0] += 1
        row[1] += input_tokens
        row[2] += output_tokens


class DailyBudget:
    def __init__(
        self,
        limit: int,
        store: UsageStore,
        *,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.limit, self.store, self.now = limit, store, now

    def today(self) -> date:
        return self.now().astimezone(IST).date()

    def check(self) -> None:
        if self.store.requests_on(self.today()) >= self.limit:
            raise BudgetExhausted(f"Daily LLM budget of {self.limit} requests reached.")

    def record(self, input_tokens: int, output_tokens: int) -> None:
        self.store.record(self.today(), input_tokens, output_tokens)

    @property
    def remaining(self) -> int:
        return max(0, self.limit - self.store.requests_on(self.today()))
