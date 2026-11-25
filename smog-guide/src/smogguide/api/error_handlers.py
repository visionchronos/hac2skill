"""FastAPI exception handlers translating domain and validation errors to HTTP.

Error responses never leak stack traces, internal URLs, or raw user input.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from types import MappingProxyType

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from smogguide.api.schemas import ErrorResponse, FieldError
from smogguide.utils.errors import (
    AirQualityUnavailableError,
    GeocodingError,
    InvalidInputError,
    LLMError,
    ServiceUnavailableError,
    SmogGuideError,
)

logger = logging.getLogger(__name__)

# Single source of truth mapping domain exception classes to HTTP status codes.
_ERROR_STATUS_MAP: Mapping[type[SmogGuideError], int] = MappingProxyType(
    {
        InvalidInputError: status.HTTP_422_UNPROCESSABLE_CONTENT,
        GeocodingError: status.HTTP_404_NOT_FOUND,
        AirQualityUnavailableError: status.HTTP_503_SERVICE_UNAVAILABLE,
        ServiceUnavailableError: status.HTTP_503_SERVICE_UNAVAILABLE,
        LLMError: status.HTTP_502_BAD_GATEWAY,
        SmogGuideError: status.HTTP_500_INTERNAL_SERVER_ERROR,
    }
)

_GENERIC_VALIDATION_MESSAGES: Mapping[str, str] = MappingProxyType(
    {
        "missing": "This field is required.",
        "extra_forbidden": "Unexpected field is not allowed.",
        "string_too_short": "Value is too short.",
        "string_too_long": "Value exceeds maximum length.",
        "enum": "Value is not one of the allowed options.",
        "bool_parsing": "Value must be a boolean.",
        "value_error": "Value failed validation rules.",
    }
)

_LOCATION_PREFIXES = frozenset({"body", "query", "path"})


def _resolve_status_code(exc: SmogGuideError) -> int:
    """Return the HTTP status code for a SmogGuideError or its closest ancestor."""
    for cls in type(exc).__mro__:
        if cls in _ERROR_STATUS_MAP:
            return _ERROR_STATUS_MAP[cls]
    return status.HTTP_500_INTERNAL_SERVER_ERROR


def _format_field_path(loc: tuple[str | int, ...]) -> str:
    """Format a Pydantic error location tuple without transport prefixes."""
    parts = [str(part) for part in loc if part not in _LOCATION_PREFIXES]
    return ".".join(parts) if parts else "request"


async def _handle_smogguide_error(request: Request, exc: Exception) -> JSONResponse:
    """Translate a SmogGuideError subclass into an ErrorResponse JSON payload."""
    if not isinstance(exc, SmogGuideError):
        return await _handle_unexpected_error(request, exc)
    http_status = _resolve_status_code(exc)
    # Never expose internal LLM failure details to end users.
    safe_message = "Advice formatting service failed." if isinstance(exc, LLMError) else exc.message
    body = ErrorResponse(error_code=exc.error_code, message=safe_message)
    return JSONResponse(status_code=http_status, content=body.model_dump())


async def _handle_validation_error(request: Request, exc: Exception) -> JSONResponse:
    """Convert FastAPI RequestValidationError into generic field_errors without echoing input."""
    if not isinstance(exc, RequestValidationError):
        return await _handle_unexpected_error(request, exc)
    field_errors = [
        FieldError(
            field=_format_field_path(err["loc"]),
            message=_GENERIC_VALIDATION_MESSAGES.get(err["type"], "Invalid value."),
        )
        for err in exc.errors()
    ]
    body = ErrorResponse(
        error_code="validation_error",
        message="Request validation failed.",
        field_errors=field_errors,
    )
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content=body.model_dump(),
    )


async def _handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    """Return a generic 500 body and log only the exception class name."""
    logger.error("Unhandled exception of type %s", type(exc).__name__)
    body = ErrorResponse(
        error_code="internal_error",
        message="An unexpected error occurred.",
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=body.model_dump(),
    )


def register_error_handlers(app: FastAPI) -> None:
    """Attach domain, validation, and catch-all error handlers to the FastAPI app."""
    app.add_exception_handler(SmogGuideError, _handle_smogguide_error)
    app.add_exception_handler(RequestValidationError, _handle_validation_error)
    app.add_exception_handler(Exception, _handle_unexpected_error)
