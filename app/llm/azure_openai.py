"""Azure OpenAI chat completions (JSON mode)."""

from __future__ import annotations

import httpx

from app.llm.base import LLMError, LLMResponse, RateLimited

API_VERSION = "2024-10-21"


def build_request(system: str, user: str, max_output_tokens: int, temperature: float) -> dict:
    return {
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "response_format": {"type": "json_object"},
        "temperature": temperature,
        "max_tokens": max_output_tokens,
    }


def parse_response(data: dict) -> LLMResponse:
    try:
        text = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError) as exc:
        raise LLMError("Azure OpenAI returned no content") from exc
    usage = data.get("usage") or {}
    return LLMResponse(text, usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0))


class AzureOpenAIProvider:
    name = "azure_openai"

    def __init__(
        self,
        endpoint: str,
        api_key: str,
        deployment: str,
        *,
        timeout: float = 60.0,
        client: httpx.Client | None = None,
    ) -> None:
        if not (endpoint and api_key and deployment):
            raise LLMError(
                "Set AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_API_KEY, and LLM_MODEL (deployment)."
            )
        self.url = f"{endpoint.rstrip('/')}/openai/deployments/{deployment}/chat/completions"
        self.client = client or httpx.Client(timeout=timeout, headers={"api-key": api_key})

    def generate(
        self, *, system: str, user: str, max_output_tokens: int, temperature: float
    ) -> LLMResponse:
        try:
            r = self.client.post(
                self.url,
                params={"api-version": API_VERSION},
                json=build_request(system, user, max_output_tokens, temperature),
            )
        except httpx.HTTPError as exc:
            raise RateLimited(f"Network error, will retry: {exc}") from exc
        if r.status_code == 429 or r.status_code >= 500:
            raise RateLimited(f"Azure OpenAI {r.status_code}")
        if r.status_code >= 400:
            raise LLMError(f"Azure OpenAI {r.status_code}: {r.text[:300]}")
        return parse_response(r.json())
