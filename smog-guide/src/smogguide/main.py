"""Application entry point and FastAPI app factory."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from smogguide import __version__
from smogguide.api.error_handlers import register_error_handlers
from smogguide.api.routes import router
from smogguide.config import Settings, get_settings


def _configure_logging(log_level: str) -> None:
    """Configure the root logger once at startup without request bodies or secrets."""
    logging.basicConfig(
        level=log_level.upper(),
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create and return a configured FastAPI application instance.

    Args:
        settings: Optional settings override; uses get_settings() when None.
    """
    resolved = settings or get_settings()
    _configure_logging(resolved.log_level)

    logger = logging.getLogger(__name__)
    logger.info("Starting SmogGuide %s (env=%s)", __version__, resolved.app_env)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        """Manage the shared HTTP client lifecycle across application startup/shutdown."""
        timeout = httpx.Timeout(resolved.http_timeout_seconds)
        limits = httpx.Limits(max_connections=100, max_keepalive_connections=20)
        client = httpx.AsyncClient(timeout=timeout, limits=limits)
        app.state.http_client = client
        logger.info("HTTP client created (timeout=%.1fs)", resolved.http_timeout_seconds)

        yield

        await client.aclose()
        logger.info("HTTP client closed")

    app = FastAPI(
        title="SmogGuide",
        version=__version__,
        description=(
            "Rule-driven air quality guidance and low-cost exposure reduction "
            "plans for families in smog-affected Indian cities."
        ),
        # Disable interactive docs in production to reduce attack surface.
        docs_url=None if resolved.app_env == "production" else "/docs",
        redoc_url=None if resolved.app_env == "production" else "/redoc",
        lifespan=lifespan,
    )
    app.state.settings = resolved

    register_error_handlers(app)
    app.include_router(router)

    if resolved.static_dir.is_dir():
        app.mount("/static", StaticFiles(directory=resolved.static_dir), name="static")
        index_path = resolved.static_dir / "index.html"
        if index_path.is_file():

            @app.get("/", include_in_schema=False)
            async def serve_index() -> FileResponse:
                """Serve the single-page frontend entry document."""
                return FileResponse(index_path)

    return app
