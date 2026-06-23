"""Application configuration via pydantic-settings.

All runtime knobs come from the environment (see .env.example). Nothing in the
codebase hardcodes a model identifier, a limit, or the provider choice; it all
flows through `Settings`.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Typed view over the process environment.

    Field names map case-insensitively to the env var names in `.env.example`
    (e.g. the field `database_url` is populated by `DATABASE_URL`).
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Core ---
    database_url: str = "postgresql+asyncpg://user:pass@localhost:5432/allocation_room"
    app_env: str = "local"

    # --- LLM ---
    llm_provider: Literal["mock", "openai"] = "mock"
    openai_api_key: str | None = None
    # DECISION: the brief leaves model ids blank in .env.example and says to pick
    # concrete Responses-API-capable ids at build time, read from config. We default
    # to sensible non-empty ids so mock mode runs with zero env setup; for
    # LLM_PROVIDER=openai these should be set explicitly in the environment.
    llm_model_strong: str = "gpt-4.1"
    llm_model_mid: str = "gpt-4.1-mini"

    max_concurrency: int = 12
    max_revisions: int = 2
    balance_threshold: int = 25
    mock_force_rebalance: bool = False

    # --- Limits (mirrored as hard caps in the input validator) ---
    max_participants: int = 20
    max_teams: int = 5
    max_team_size: int = 4
    # DECISION (Part 4): rounds are bounded at the service layer to cap generation
    # cost; per-round decision counts and team sizes are already capped in Part 1.
    max_rounds: int = 6

    # --- API hardening / integration (Part 4) ---
    # Comma-separated allowed origins for the browser frontend (CORS).
    cors_allow_origins: str = "http://localhost:5173,http://localhost:4173"
    # Simple in-process fixed-window rate limit; disabled when app_env == "test".
    rate_limit_per_minute: int = 120

    # --- Auth (email/password -> JWT bearer token) ---
    # Override JWT_SECRET in production. HS256 is signed with this secret.
    jwt_secret: str = "dev-insecure-change-me-please"
    jwt_expire_minutes: int = 60 * 24 * 7  # one week

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_allow_origins.split(",") if o.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a process-wide cached Settings instance."""
    return Settings()
