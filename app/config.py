"""Application configuration via pydantic-settings.

All runtime knobs come from the environment (see .env.example). Nothing in the
codebase hardcodes a model identifier, a limit, or the provider choice; it all
flows through `Settings`.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from pydantic import field_validator, model_validator
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
    # Dev-only escape hatch: when true, requests may name their tenant via the
    # X-Tenant-Id header WITHOUT a signed JWT. This bypasses authentication and
    # must never be enabled in production. Defaults OFF; auto-allowed only in
    # local/test below.
    allow_header_tenant: bool = False

    # --- LLM ---
    llm_provider: Literal["mock", "openai", "claude"] = "mock"
    openai_api_key: str | None = None
    # DECISION: the brief leaves model ids blank in .env.example and says to pick
    # concrete Responses-API-capable ids at build time, read from config. We default
    # to sensible non-empty ids so mock mode runs with zero env setup; for
    # LLM_PROVIDER=openai these should be set explicitly in the environment.
    llm_model_strong: str = "gpt-4.1"
    llm_model_mid: str = "gpt-4.1-mini"

    # --- Anthropic / Claude (used when LLM_PROVIDER=claude) ---
    # OpenAI stays configured alongside these; flipping LLM_PROVIDER is all it takes.
    # Point the strong/mid ids at whichever Claude models you want (e.g. Opus, Fable).
    anthropic_api_key: str | None = None
    anthropic_model_strong: str = "claude-opus-4-8"
    anthropic_model_mid: str = "claude-opus-4-8"
    anthropic_max_tokens: int = 8192

    @model_validator(mode="after")
    def _select_active_models(self) -> "Settings":
        # Keep the pipeline provider-agnostic: it always reads llm_model_strong /
        # llm_model_mid. When Claude is active, those resolve to the Anthropic ids
        # (the OpenAI/GPT ids stay configured for when you flip back).
        if self.llm_provider == "claude":
            self.llm_model_strong = self.anthropic_model_strong
            self.llm_model_mid = self.anthropic_model_mid
        return self

    @model_validator(mode="after")
    def _resolve_header_tenant(self) -> "Settings":
        # Convenience: in local/test/dev, allow the X-Tenant-Id fallback so tooling
        # (Postman, the test suite) works without minting JWTs. Outside dev it is
        # force-disabled even if someone sets ALLOW_HEADER_TENANT=true, so the
        # auth bypass can never reach production by misconfiguration.
        dev_envs = {"local", "test", "dev", "development", "ci"}
        if self.app_env.lower() in dev_envs:
            self.allow_header_tenant = True
        else:
            self.allow_header_tenant = False
        return self

    @model_validator(mode="after")
    def _guard_jwt_secret(self) -> "Settings":
        # Fail loudly instead of silently booting with an insecure JWT secret in a
        # non-dev environment. In prod, set JWT_SECRET to a strong, unique value.
        dev_envs = {"local", "test", "dev", "development", "ci"}
        insecure = {"", "dev-insecure-change-me-please"}
        if self.app_env.lower() not in dev_envs and self.jwt_secret in insecure:
            raise ValueError(
                "JWT_SECRET must be set to a strong, unique value when APP_ENV is not "
                f"local/test (APP_ENV={self.app_env!r}); refusing to start with the "
                'insecure default. Generate one: python -c "import secrets; '
                'print(secrets.token_urlsafe(48))"'
            )
        return self

    max_concurrency: int = 12
    # How many participants are generated concurrently per wave in the fan-out.
    # Small on purpose: with 40-50 distinct roles this bounds model load and keeps
    # progress readable, while max_concurrency still caps total in-flight LLM calls.
    participant_batch_size: int = 3
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

    # --- Cloudinary (image hosting for simulation assets) ---
    cloudinary_cloud_name: str = ""
    cloudinary_api_key: str = ""
    cloudinary_api_secret: str = ""

    @property
    def cloudinary_configured(self) -> bool:
        return bool(
            self.cloudinary_cloud_name and self.cloudinary_api_key and self.cloudinary_api_secret
        )

    @field_validator("database_url", mode="before")
    @classmethod
    def _normalize_database_url(cls, value: str) -> str:
        # Accept plain postgresql:// in envs and force asyncpg for runtime.
        # Also translate psycopg-style SSL query args to asyncpg-compatible ones.
        if not isinstance(value, str):
            return value

        url = value
        if url.startswith("postgresql://"):
            url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
        if not url.startswith("postgresql+asyncpg://"):
            return url

        parsed = urlsplit(url)
        query_pairs = parse_qsl(parsed.query, keep_blank_values=True)
        query_map = {k: v for k, v in query_pairs}

        sslmode = query_map.pop("sslmode", None)
        if sslmode is not None and "ssl" not in query_map:
            # asyncpg expects "ssl", not psycopg's "sslmode".
            if sslmode.lower() in {"disable", "allow", "prefer"}:
                query_map["ssl"] = "false"
            else:
                query_map["ssl"] = "require"

        # psycopg-specific; asyncpg does not accept this query arg.
        query_map.pop("channel_binding", None)

        new_query = urlencode(query_map)
        return urlunsplit(
            (parsed.scheme, parsed.netloc, parsed.path, new_query, parsed.fragment)
        )

    @field_validator("cors_allow_origins", mode="before")
    @classmethod
    def _normalize_cors_allow_origins(cls, value: str) -> str:
        if not isinstance(value, str):
            return value
        normalized: list[str] = []
        for origin in value.split(","):
            o = origin.strip()
            if not o:
                continue
            if "://" not in o:
                if o.startswith("localhost") or o.startswith("127.0.0.1"):
                    o = f"http://{o}"
                else:
                    o = f"https://{o}"
            normalized.append(o)
        return ",".join(normalized)

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_allow_origins.split(",") if o.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a process-wide cached Settings instance."""
    return Settings()