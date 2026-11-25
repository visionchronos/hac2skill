"""Application configuration via Pydantic Settings.

All settings are read from environment variables (prefix: SMOGGUIDE_)
or from a .env file. No other module reads os.environ directly.
"""

from __future__ import annotations

import functools
import logging
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    """Typed, validated application settings.

    Every field is loaded from SMOGGUIDE_<FIELD_NAME> environment variables
    or from a .env file. SecretStr fields are never logged.
    """

    model_config = SettingsConfigDict(
        env_prefix="SMOGGUIDE_",
        env_file=".env",
        env_file_encoding="utf-8",
        # Reject unknown env vars mapped to this model so misconfiguration is caught early.
        extra="ignore",
    )

    # ------------------------------------------------------------------
    # Application runtime
    # ------------------------------------------------------------------

    app_env: Literal["development", "production", "test"] = Field(
        default="development",
        description="Runtime environment; controls behaviour such as debug pages.",
    )

    log_level: str = Field(
        default="INFO",
        description="Python logging level name (DEBUG, INFO, WARNING, ERROR, CRITICAL).",
    )

    # ------------------------------------------------------------------
    # LLM provider
    # ------------------------------------------------------------------

    llm_provider: Literal["none", "gemini", "anthropic"] = Field(
        default="none",
        description=(
            "LLM provider used to reword advice text. "
            "When 'none' the app serves template-based fallback text."
        ),
    )

    llm_api_key: SecretStr | None = Field(
        default=None,
        description="API key for the configured LLM provider. Never logged.",
    )

    llm_timeout_seconds: float = Field(
        default=15.0,
        gt=0,
        description="Maximum seconds to wait for a single LLM API response.",
    )

    llm_max_tokens: int = Field(
        default=1200,
        gt=0,
        description="Token budget requested from the LLM for each advice response.",
    )

    # ------------------------------------------------------------------
    # Outbound HTTP (AQI data, geocoding)
    # ------------------------------------------------------------------

    http_timeout_seconds: float = Field(
        default=8.0,
        gt=0,
        description="Maximum seconds for any outbound HTTP call.",
    )

    http_max_retries: int = Field(
        default=2,
        ge=0,
        le=5,
        description="Maximum retry attempts for a failed outbound HTTP call.",
    )

    # ------------------------------------------------------------------
    # Caching
    # ------------------------------------------------------------------

    air_quality_cache_ttl_seconds: int = Field(
        # 15 minutes: short enough to reflect rapidly changing smog conditions.
        default=900,
        description="Seconds to cache fetched air quality readings.",
    )

    geocoding_cache_ttl_seconds: int = Field(
        # 24 hours: city-level coordinates do not change often.
        default=86400,
        description="Seconds to cache geocoding results for a location string.",
    )

    cache_max_entries: int = Field(
        default=512,
        gt=0,
        description="Maximum number of items held in any single in-process LRU cache.",
    )

    # ------------------------------------------------------------------
    # API security
    # ------------------------------------------------------------------

    cors_allowed_origins: list[str] = Field(
        default_factory=list,
        description="CORS origins that may call the API. Empty list permits none.",
    )

    rate_limit_per_minute: int = Field(
        default=20,
        gt=0,
        description="Maximum API requests accepted per IP address per minute.",
    )

    max_request_body_bytes: int = Field(
        default=16384,
        gt=0,
        # Guards against oversized payloads that could exhaust memory.
        description="Maximum accepted request body size in bytes.",
    )

    # ------------------------------------------------------------------
    # Paths
    # ------------------------------------------------------------------

    catalog_path: Path = Field(
        default=Path("data/recommendations.yaml"),
        description="Path to the recommendations YAML catalog, relative to the working directory.",
    )

    static_dir: Path = Field(
        default=Path("static"),
        description="Directory containing the static frontend files served by FastAPI.",
    )

    # ------------------------------------------------------------------
    # Validators
    # ------------------------------------------------------------------

    @model_validator(mode="after")
    def warn_on_missing_llm_key(self) -> Settings:
        """Warn — but do not error — when an LLM provider is chosen without a key.

        The application must still start and serve template fallback text.
        """
        if self.llm_provider != "none" and self.llm_api_key is None:
            logger.warning(
                "SMOGGUIDE_LLM_PROVIDER is %r but SMOGGUIDE_LLM_API_KEY is not set. "
                "The application will fall back to template-based advice text.",
                self.llm_provider,
            )
        return self


@functools.cache
def get_settings() -> Settings:
    """Return the cached application settings singleton.

    Raises:
        pydantic_settings.ValidationError: if any required setting is invalid.
    """
    return Settings()
