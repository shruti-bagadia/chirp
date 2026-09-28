"""Typed configuration from environment variables (.env locally)."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    chirp_env: Literal["local", "staging", "production", "test"] = "local"
    version: str = "0.1.0"
    owner_first_name: str = "friend"

    # Auth
    session_secret: SecretStr = SecretStr("dev-only-change-me")
    dashboard_password_hash: str = ""
    chirp_api_token: SecretStr = SecretStr("")

    # Data
    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/chirp"
    supabase_url: str = ""
    supabase_service_key: SecretStr = SecretStr("")
    storage_bucket: str = "chirp-files"

    # LLM
    llm_provider: Literal["gemini", "azure_openai", "mock"] = "gemini"
    llm_model: str = ""
    gemini_api_key: SecretStr = SecretStr("")
    azure_openai_endpoint: str = ""
    azure_openai_api_key: SecretStr = SecretStr("")
    llm_daily_request_budget: int = Field(900, ge=1)
    llm_requests_per_minute: int = Field(10, ge=1)

    # Manual runs
    github_dispatch_token: SecretStr = SecretStr("")
    github_repo: str = ""

    # Applier
    apply_dry_run: bool = True

    # Gmail (P1): job-alert email discovery
    gmail_client_id: str = ""
    gmail_client_secret: SecretStr = SecretStr("")
    gmail_refresh_token: SecretStr = SecretStr("")
    gmail_label: str = "job-alerts"
    gmail_applications_label: str = "applications-sent"

    @property
    def is_production(self) -> bool:
        return self.chirp_env == "production"

    def check_production_ready(self) -> list[str]:
        """Names of settings that must be set before running in production."""
        missing = []
        if self.session_secret.get_secret_value() == "dev-only-change-me":
            missing.append("SESSION_SECRET")
        if not self.dashboard_password_hash:
            missing.append("DASHBOARD_PASSWORD_HASH")
        if not self.chirp_api_token.get_secret_value():
            missing.append("CHIRP_API_TOKEN")
        return missing


@lru_cache
def get_settings() -> Settings:
    return Settings()
