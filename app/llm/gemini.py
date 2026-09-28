"""Google Gemini (Generative Language API, REST)."""

from __future__ import annotations

import httpx

from app.llm.base import LLMError, LLMResponse, RateLimited

API = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


def build_request(system: str, user: str, max_output_tokens: int, temperature: float) -> dict:
    return {
        "systemInstruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": [{"text": user}]}],
        "generationConfig": {
            "responseMimeType": "application/json",
            "temperature": temperature,
            "maxOutputTokens": max_output_tokens,
        },
    }


def parse_response(data: dict) -> LLMResponse:
    try:
        parts = data["candidates"][0]["content"]["parts"]
    except (KeyError, IndexError) as exc:
        reason = (data.get("promptFeedback") or {}).get("blockReason") or "no candidates"
        raise LLMError(f"Gemini returned no text ({reason})") from exc
    text = "".join(p.get("text", "") for p in parts)
    usage = data.get("usageMetadata") or {}
    return LLMResponse(text, usage.get("promptTokenCount", 0), usage.get("candidatesTokenCount", 0))


class GeminiProvider:
    name = "gemini"

    def __init__(
        self, api_key: str, model: str, *, timeout: float = 60.0, client: httpx.Client | None = None
    ) -> None:
        if not api_key or not model:
            raise LLMError("Set GEMINI_API_KEY and LLM_MODEL to use Gemini.")
        self.model = model
        self.client = client or httpx.Client(timeout=timeout, headers={"x-goog-api-key": api_key})

    def generate(
        self, *, system: str, user: str, max_output_tokens: int, temperature: float
    ) -> LLMResponse:
        try:
            r = self.client.post(
                API.format(model=self.model),
                json=build_request(system, user, max_output_tokens, temperature),
            )
        except httpx.HTTPError as exc:
            raise RateLimited(f"Network error, will retry: {exc}") from exc
        if r.status_code == 429 or r.status_code >= 500:
            raise RateLimited(f"Gemini {r.status_code}")
        if r.status_code >= 400:
            raise LLMError(f"Gemini {r.status_code}: {r.text[:300]}")
        return parse_response(r.json())
