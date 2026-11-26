"""Application configuration loaded from environment variables / .env file."""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import AliasChoices, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central settings object.

    All fields are populated from environment variables (case-insensitive) or
    from a ``.env`` file in the working directory.  Production deployments should
    supply values via environment variables only; the ``.env`` file is provided
    as a convenience for local development.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ------------------------------------------------------------------ #
    # Infrastructure                                                       #
    # ------------------------------------------------------------------ #

    DATABASE_URL: str
    """Async-compatible PostgreSQL DSN.

    Example: ``postgresql+asyncpg://user:password@localhost:5432/consulting``
    """

    REDIS_URL: str = "redis://localhost:6379/0"
    """Redis connection URL used by both the application cache and Celery."""

    SECRET_KEY: str
    """Random secret used for signing tokens / sessions.

    Generate with: ``python -c "import secrets; print(secrets.token_hex(32))"``
    """

    ENVIRONMENT: Literal["development", "staging", "production"] = "development"
    """Deployment environment – controls logging format, debug flags, etc."""

    LOG_LEVEL: str = "INFO"
    """Python logging level name (DEBUG, INFO, WARNING, ERROR, CRITICAL)."""

    # ------------------------------------------------------------------ #
    # Celery                                                               #
    # ------------------------------------------------------------------ #

    CELERY_BROKER_URL: str
    """Celery broker DSN.  Typically the same value as ``REDIS_URL``."""

    CELERY_RESULT_BACKEND: str
    """Celery result-backend DSN.  Typically the same value as ``REDIS_URL``."""

    # ------------------------------------------------------------------ #
    # LLM / AI                                                            #
    # ------------------------------------------------------------------ #

    LLM_PROVIDER: str = "gemini"
    """Name of the LLM provider to use (e.g. ``gemini``, ``openai``, ``mock``)."""

    GEMINI_API_KEY: SecretStr = Field(
        default=SecretStr(""),
        validation_alias=AliasChoices("GEMINI_API_KEY", "GOOGLE_API_KEY", "GEMINI_KEY"),
    )
    """Google Gemini API key. Stored as a ``SecretStr`` so it is never logged."""

    GEMINI_MODEL: str = Field(
        default="gemini-3.6-flash",
        validation_alias=AliasChoices("GEMINI_MODEL", "GOOGLE_MODEL"),
    )
    """Google Gemini model name (defaults to ``gemini-3.6-flash``)."""

    OPENAI_API_KEY: SecretStr = SecretStr("")
    """OpenAI API key.  Stored as a ``SecretStr`` so it is never logged."""

    # ------------------------------------------------------------------ #
    # Search                                                               #
    # ------------------------------------------------------------------ #

    SEARCH_PROVIDER: str = "serpapi"
    """Name of the web-search provider (e.g. ``serpapi``, ``google``)."""

    SERPAPI_KEY: SecretStr = Field(
        default=SecretStr(""),
        validation_alias=AliasChoices("SERPAPI_KEY", "SERPAPI_API_KEY"),
    )
    """SerpAPI key.  Stored as a ``SecretStr`` so it is never logged."""

    # ------------------------------------------------------------------ #
    # Observability – Langfuse                                            #
    # ------------------------------------------------------------------ #

    LANGFUSE_PUBLIC_KEY: SecretStr = SecretStr("")
    """Langfuse project public key."""

    LANGFUSE_SECRET_KEY: SecretStr = SecretStr("")
    """Langfuse project secret key."""

    LANGFUSE_HOST: str = "https://cloud.langfuse.com"
    """Langfuse ingestion host."""

    # ------------------------------------------------------------------ #
    # Webhooks & External Notifications                                  #
    # ------------------------------------------------------------------ #

    SLACK_WEBHOOK_URL: Optional[str] = None
    """Default incoming webhook URL for Slack review gate alerts."""

    TEAMS_WEBHOOK_URL: Optional[str] = None
    """Default incoming webhook URL for MS Teams review gate alerts."""

    FRONTEND_BASE_URL: str = "http://localhost:3000"
    """Base URL for the frontend UI used in webhook deep links."""

    ARTIFACT_RETENTION_DAYS: int = 7
    """Number of days to retain generated deliverable artifacts before scheduled cleanup."""

    # ------------------------------------------------------------------ #
    # Helpers                                                              #
    # ------------------------------------------------------------------ #

    @property
    def SERPAPI_API_KEY(self) -> SecretStr:
        """Alias property for SERPAPI_KEY."""
        return self.SERPAPI_KEY

    @property
    def is_production(self) -> bool:
        """Return ``True`` when running in the production environment."""
        return self.ENVIRONMENT == "production"

    @property
    def is_development(self) -> bool:
        """Return ``True`` when running in the development environment."""
        return self.ENVIRONMENT == "development"


# ---------------------------------------------------------------------------
# Module-level singleton – import this everywhere instead of instantiating
# Settings() directly.
# ---------------------------------------------------------------------------

settings = Settings()  # type: ignore[call-arg]
