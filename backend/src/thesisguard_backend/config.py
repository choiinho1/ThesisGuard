"""Environment-driven settings. Values come from backend/.env (never committed)."""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://thesisguard:thesisguard@localhost:5432/thesisguard"

    jwt_secret_key: str = "change-me"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60

    # Google Identity Services web Client ID; must match frontend's
    # NEXT_PUBLIC_GOOGLE_CLIENT_ID (Google Client IDs are not secret, but the
    # backend needs it to verify the "aud" claim on incoming ID tokens).
    google_client_id: str | None = None

    llm_provider: str = "openai"
    llm_model: str = "gpt-4o-mini"
    openai_api_key: str | None = None
    google_api_key: str | None = None

    # Optional LLM observability. No data leaves the app unless explicitly
    # enabled and both project keys are configured.
    langfuse_enabled: bool = False
    langfuse_public_key: str | None = None
    langfuse_secret_key: str | None = None
    langfuse_base_url: str = "https://cloud.langfuse.com"
    langfuse_tracing_environment: str = "development"
    langfuse_sample_rate: float = 1.0
    langfuse_debug: bool = False

    sec_user_agent: str = "ThesisGuard PBL Team <you@example.com>"
    fred_base_url: str = "https://fred.stlouisfed.org/graph/fredgraph.csv"

    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_from_email: str = "alerts@thesisguard.local"
    smtp_use_tls: bool = True
    email_dry_run: bool = True
    scheduler_enabled: bool = True
    scheduler_poll_seconds: int = 60


@lru_cache
def get_settings() -> Settings:
    return Settings()
