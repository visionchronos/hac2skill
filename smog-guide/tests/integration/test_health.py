"""Integration tests for the /health endpoint."""

from __future__ import annotations

from fastapi.testclient import TestClient

from smogguide import __version__


def test_health_returns_200(client: TestClient) -> None:
    """GET /health must respond with HTTP 200."""
    response = client.get("/health")
    assert response.status_code == 200


def test_health_body_contains_ok_status(client: TestClient) -> None:
    """GET /health body must contain status 'ok'."""
    response = client.get("/health")
    assert response.json()["status"] == "ok"


def test_health_body_contains_version(client: TestClient) -> None:
    """GET /health body must report the current package version."""
    response = client.get("/health")
    assert response.json()["version"] == __version__
