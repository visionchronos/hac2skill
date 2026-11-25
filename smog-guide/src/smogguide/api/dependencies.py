"""FastAPI dependency providers for settings, HTTP client, and services."""

from __future__ import annotations

import httpx
from fastapi import Request

from smogguide.config import Settings, get_settings
from smogguide.services.advice_service import AdviceService
from smogguide.utils.errors import ServiceUnavailableError


def get_settings_dep(request: Request) -> Settings:
    """Return the application Settings instance bound to app state or default singleton."""
    settings = getattr(request.app.state, "settings", None)
    if isinstance(settings, Settings):
        return settings
    return get_settings()


def get_http_client(request: Request) -> httpx.AsyncClient:
    """Return the shared AsyncClient stored on app.state during lifespan startup."""
    client = getattr(request.app.state, "http_client", None)
    if not isinstance(client, httpx.AsyncClient):
        raise ServiceUnavailableError("HTTP client is not initialized.")
    return client


def get_advice_service(request: Request) -> AdviceService:
    """Return the configured AdviceService from app.state or raise 503-mapped error."""
    service = getattr(request.app.state, "advice_service", None)
    if service is None:
        raise ServiceUnavailableError("Advice service is not configured")
    return service  # type: ignore[no-any-return]
