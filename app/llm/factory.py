"""Build the configured provider and client."""

from __future__ import annotations

from app.core.config import Settings
from app.llm.base import LLMError, LLMProvider


def make_provider(s: Settings) -> LLMProvider:
    if s.llm_provider == "gemini":
        from app.llm.gemini import GeminiProvider

        return GeminiProvider(s.gemini_api_key.get_secret_value(), s.llm_model)
    if s.llm_provider == "azure_openai":
        from app.llm.azure_openai import AzureOpenAIProvider

        return AzureOpenAIProvider(
            s.azure_openai_endpoint, s.azure_openai_api_key.get_secret_value(), s.llm_model
        )
    if s.llm_provider == "mock":
        from app.llm.mock import MockProvider, smart_default

        return MockProvider(default=smart_default)
    raise LLMError(f"Unknown LLM_PROVIDER: {s.llm_provider}")
