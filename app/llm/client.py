"""Every LLM call goes through here: redact, rate-limit, budget, call, parse, validate, restore."""

from __future__ import annotations

import json
import random
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, TypeVar

from app.llm.base import LLMError, LLMProvider, RateLimited, SchemaError
from app.llm.pii import Redactor
from app.llm.ratelimit import DailyBudget, TokenBucket

T = TypeVar("T")


def parse_json(text: str) -> Any:
    """Parse model output, tolerating ```json fences and text around the object."""
    cleaned = re.sub(r"```(?:json)?", "", text).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start >= 0 and end > start:
            try:
                return json.loads(cleaned[start : end + 1])
            except json.JSONDecodeError as exc:
                raise SchemaError(f"Output wasn't valid JSON: {exc}") from exc
        raise SchemaError("Output wasn't valid JSON.") from None


def _restore(obj: Any, redactor: Redactor) -> Any:
    if isinstance(obj, str):
        return redactor.restore(obj)
    if isinstance(obj, list):
        return [_restore(x, redactor) for x in obj]
    if isinstance(obj, dict):
        return {k: _restore(v, redactor) for k, v in obj.items()}
    return obj


@dataclass
class CallStats:
    requests: int = 0
    retries: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    sent: list[str] = field(default_factory=list)  # redacted request bodies, for audits and tests


class LLMClient:
    def __init__(
        self,
        provider: LLMProvider,
        redactor: Redactor,
        bucket: TokenBucket,
        budget: DailyBudget,
        *,
        max_rate_retries: int = 3,
        sleep: Callable[[float], None] = time.sleep,
        keep_requests: bool = False,
    ) -> None:
        self.provider, self.redactor, self.bucket, self.budget = provider, redactor, bucket, budget
        self.max_rate_retries, self.sleep, self.keep_requests = (
            max_rate_retries,
            sleep,
            keep_requests,
        )
        self.stats = CallStats()

    def _call(self, system: str, user: str, max_output_tokens: int, temperature: float) -> str:
        for attempt in range(self.max_rate_retries + 1):
            self.budget.check()
            self.bucket.acquire()
            try:
                resp = self.provider.generate(
                    system=system,
                    user=user,
                    max_output_tokens=max_output_tokens,
                    temperature=temperature,
                )
            except RateLimited:
                if attempt == self.max_rate_retries:
                    raise
                self.sleep((2**attempt) + random.random())
                self.stats.retries += 1
                continue
            self.budget.record(resp.input_tokens, resp.output_tokens)
            self.stats.requests += 1
            self.stats.input_tokens += resp.input_tokens
            self.stats.output_tokens += resp.output_tokens
            return resp.text
        raise LLMError("Unreachable")

    def generate(
        self,
        *,
        system: str,
        user: str,
        parse: Callable[[dict], T],
        max_output_tokens: int = 2048,
        temperature: float = 0.2,
    ) -> T:
        """Call the model and return `parse(json)`. One retry if the shape is wrong."""
        system_r, user_r = self.redactor.redact(system), self.redactor.redact(user)
        leaks = self.redactor.leaks(system_r + user_r)
        if leaks:
            raise LLMError(f"Refusing to send personal details: {leaks}")
        if self.keep_requests:
            self.stats.sent.append(system_r + "\n---\n" + user_r)

        text = self._call(system_r, user_r, max_output_tokens, temperature)
        try:
            return parse(_restore(parse_json(text), self.redactor))
        except SchemaError as first:
            self.stats.retries += 1
            fix = (
                f"{user_r}\n\nYour previous reply was rejected: {first}. "
                "Reply again with only the corrected JSON."
            )
            text = self._call(system_r, fix, max_output_tokens, temperature)
            return parse(_restore(parse_json(text), self.redactor))
