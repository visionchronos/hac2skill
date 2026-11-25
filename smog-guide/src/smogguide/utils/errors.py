"""Custom exception hierarchy for SmogGuide.

All application errors derive from SmogGuideError so the API layer can
translate them to HTTP responses without leaking internals or swallowing
unexpected exceptions. No HTTP status codes or framework imports live here.
"""

from __future__ import annotations

from typing import ClassVar


class SmogGuideError(Exception):
    """Base class for all SmogGuide application errors.

    Attributes:
        message: Safe, user-presentable error summary.
        error_code: Stable machine-readable identifier for the error category.
    """

    error_code: ClassVar[str] = "smogguide_error"

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class InvalidInputError(SmogGuideError):
    """Raised when incoming data fails domain-level validation rules."""

    error_code: ClassVar[str] = "invalid_input"


class GeocodingError(SmogGuideError):
    """Raised when a location cannot be resolved or the geocoder fails."""

    error_code: ClassVar[str] = "geocoding_failed"


class AirQualityUnavailableError(SmogGuideError):
    """Raised when the air quality provider fails or returns invalid data."""

    error_code: ClassVar[str] = "air_quality_unavailable"


class LLMError(SmogGuideError):
    """Raised on LLM provider failures; never surfaced to users directly."""

    error_code: ClassVar[str] = "llm_error"


class CatalogError(SmogGuideError):
    """Raised at startup when the recommendations catalog is missing or malformed."""

    error_code: ClassVar[str] = "catalog_error"


class ServiceUnavailableError(SmogGuideError):
    """Raised when a required upstream dependency is temporarily unavailable."""

    error_code: ClassVar[str] = "service_unavailable"
