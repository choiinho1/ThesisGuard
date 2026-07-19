"""Environment-driven settings. Values come from backend/.env (never committed)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://thesisguard:thesisguard@localhost:5432/thesisguard"

    jwt_secret_key: str = "change-me"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    @property
    def cors_origin_list(self) -> list[str]:
        return [
            origin.strip().rstrip("/") for origin in self.cors_origins.split(",") if origin.strip()
        ]

    # Google Identity Services web Client ID; must match frontend's
    # NEXT_PUBLIC_GOOGLE_CLIENT_ID (Google Client IDs are not secret, but the
    # backend needs it to verify the "aud" claim on incoming ID tokens).
    google_client_id: str | None = None

    llm_provider: str = "openai"
    llm_model: str = "gpt-4o-mini"
    openai_api_key: str | None = None
    google_api_key: str | None = None
    upstage_api_key: str | None = None
    rag_enabled: bool = True
    rag_embedding_provider: str = "openai"
    openai_embedding_model: str = "text-embedding-3-small"
    upstage_embedding_model: str = "solar-embedding-1-large"
    rag_embedding_timeout_seconds: float = 20

    # Persistent semantic index used by portfolio Q&A. With no URL, the
    # official Qdrant client stores vectors on disk for zero-setup local use.
    qdrant_url: str | None = None
    qdrant_api_key: str | None = None
    qdrant_path: Path = Path(__file__).resolve().parents[2] / "data" / "qdrant"
    qdrant_evidence_collection: str = "thesisguard_evidence_v1"
    portfolio_qa_semantic_limit: int = 20
    portfolio_qa_score_threshold: float | None = None

    # Materialized, prompt-ready evidence history. Files are derived from DB
    # state and kept outside source control.
    evidence_history_dir: Path = Path(__file__).resolve().parents[2] / "data" / "evidence_history"
    evidence_history_max_items: int = 30

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
