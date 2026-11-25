"""Unit tests for application configuration loading and validation."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from smogguide.config import Settings


def test_config_defaults_load() -> None:
    """Settings constructed with no arguments should load without error."""
    settings = Settings()
    assert settings.app_env == "development"
    assert settings.llm_provider == "none"
    assert settings.llm_api_key is None
    assert settings.http_timeout_seconds == 8.0
    assert settings.http_max_retries == 2
    assert settings.cache_max_entries == 512


def test_config_negative_timeout_is_rejected() -> None:
    """A non-positive timeout value must raise a ValidationError at construction time."""
    with pytest.raises(ValidationError):
        Settings(http_timeout_seconds=-1.0)


def test_config_zero_timeout_is_rejected() -> None:
    """Zero is also not a valid timeout (gt=0 constraint)."""
    with pytest.raises(ValidationError):
        Settings(llm_timeout_seconds=0.0)


def test_config_retries_above_max_is_rejected() -> None:
    """http_max_retries must be at most 5."""
    with pytest.raises(ValidationError):
        Settings(http_max_retries=99)


def test_config_negative_retries_is_rejected() -> None:
    """http_max_retries must be non-negative."""
    with pytest.raises(ValidationError):
        Settings(http_max_retries=-1)


def test_config_missing_llm_key_does_not_crash() -> None:
    """Choosing a real LLM provider without a key must only warn, not raise."""
    # Should not raise; the validator logs a warning and returns self.
    settings = Settings(llm_provider="gemini", llm_api_key=None)
    assert settings.llm_provider == "gemini"
    assert settings.llm_api_key is None


def test_config_test_env_accepted() -> None:
    """The 'test' app_env literal must be a valid value."""
    settings = Settings(app_env="test")
    assert settings.app_env == "test"


def test_config_invalid_app_env_is_rejected() -> None:
    """An unrecognised app_env value must raise a ValidationError."""
    with pytest.raises(ValidationError):
        Settings(app_env="staging")  # type: ignore[arg-type]
