"""LLM provider interface. Providers return parsed JSON; validation happens in the client."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class LLMError(RuntimeError):
    """Provider failed in a way retrying won't fix."""


class RateLimited(LLMError):
    """Provider said slow down (HTTP 429)."""


class BudgetExhausted(LLMError):
    """Today's request budget is used up. Stop the run cleanly."""


class SchemaError(ValueError):
    """Model output didn't match the expected shape."""


@dataclass(slots=True)
class LLMResponse:
    text: str
    input_tokens: int = 0
    output_tokens: int = 0


class LLMProvider(Protocol):
    name: str

    def generate(
        self, *, system: str, user: str, max_output_tokens: int, temperature: float
    ) -> LLMResponse: ...


class EmbeddingProvider(Protocol):
    """Turns text into vectors for answer-bank matching. Runs locally (the Applier,
    or a `chirp` CLI command) — never on the dashboard process. See docs/07_llm_layer.md."""

    dim: int

    def embed(self, texts: list[str]) -> list[list[float]]: ...
