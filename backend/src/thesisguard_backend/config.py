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

    llm_provider: str = "openai"
    llm_model: str = "gpt-4o-mini"
    openai_api_key: str | None = None

    sec_user_agent: str = "ThesisGuard PBL Team <you@example.com>"
    fred_base_url: str = "https://fred.stlouisfed.org/graph/fredgraph.csv"
    stooq_base_url: str = "https://stooq.com"

    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_from_email: str = "alerts@thesisguard.local"
    smtp_use_tls: bool = True
    email_dry_run: bool = True


@lru_cache
def get_settings() -> Settings:
    return Settings()
