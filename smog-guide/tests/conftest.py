"""Shared pytest fixtures for the SmogGuide test suite."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from smogguide.config import Settings
from smogguide.main import create_app


@pytest.fixture()
def test_settings() -> Settings:
    """Return minimal Settings configured for the test environment."""
    return Settings(app_env="test", log_level="WARNING")


@pytest.fixture()
def app(test_settings: Settings) -> FastAPI:
    """Return a FastAPI test application instance."""
    return create_app(settings=test_settings)


@pytest.fixture()
def client(app: FastAPI) -> TestClient:
    """Return a synchronous TestClient wrapping the test application."""
    return TestClient(app)
