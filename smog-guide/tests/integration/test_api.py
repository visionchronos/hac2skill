"""Integration tests for the SmogGuide API routes, schemas, and error mapping."""

from __future__ import annotations

import logging

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from smogguide.api.dependencies import get_advice_service
from smogguide.config import Settings
from smogguide.main import create_app
from smogguide.utils.errors import (
    AirQualityUnavailableError,
    GeocodingError,
    LLMError,
)
from tests.fixtures.fake_advice import FakeAdviceService


def _app_with_fake(fake: FakeAdviceService) -> FastAPI:
    app = create_app(settings=Settings(app_env="test", log_level="WARNING"))
    app.dependency_overrides[get_advice_service] = lambda: fake
    return app


def test_api_advice_happy_path_returns_full_shape() -> None:
    """POST /api/v1/advice returns 200 and the complete AdviceResponse contract."""
    fake = FakeAdviceService()
    client = TestClient(_app_with_fake(fake))

    response = client.post(
        "/api/v1/advice",
        json={
            "city": "  New   Delhi  ",
            "profile": {"has_children": True, "budget_tier": "free"},
            "language": "hi",
            "notes": "  ground floor  ",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["air"]["location"] == "New Delhi"
    assert body["air"]["pm25"] == 210.0
    assert body["air"]["pm10"] == 310.0
    assert body["air"]["us_aqi"] == 260
    assert body["risk"]["level"] == "very_poor"
    assert body["risk"]["label"] == "Very Poor"
    assert body["risk"]["plain_meaning"]
    assert body["risk"]["icon_name"]
    assert body["cleanest_window"]["mean_pm25"] == pytest.approx(150.0)
    assert len(body["routine"]) == 1
    assert len(body["indoor"]) == 1
    assert len(body["alternatives"]) == 1
    assert body["routine"][0]["impact"]["source"] == "general guidance"
    assert body["plan_impact"]["exposure_without_plan"]["unit"] == "ug/m3"
    assert body["generated_by"] == "rules"
    assert body["disclaimer"]
    assert fake.last_advice_args is not None
    assert fake.last_advice_args[0] == "New Delhi"
    assert fake.last_advice_args[3] == "ground floor"


def test_api_aqi_happy_path_returns_full_shape() -> None:
    """GET /api/v1/aqi returns 200 and the complete AirSummaryResponse contract."""
    fake = FakeAdviceService()
    client = TestClient(_app_with_fake(fake))

    response = client.get("/api/v1/aqi", params={"city": "नई दिल्ली"})

    assert response.status_code == 200
    body = response.json()
    assert body["location"] == "नई दिल्ली"
    assert body["pm25"] == 210.0
    assert body["pm10"] == 310.0
    assert body["us_aqi"] == 260
    assert body["risk_level"] == "very_poor"
    assert body["risk_label"] == "Very Poor"
    assert body["plain_meaning"]
    assert body["icon_name"]
    assert body["observed_at"]
    assert body["cleanest_window"]["mean_pm25"] == pytest.approx(150.0)


@pytest.mark.parametrize(
    ("payload", "forbidden_echo"),
    [
        ({"city": ""}, None),
        ({"city": "Delhi123"}, "Delhi123"),
        ({"city": "a" * 81}, "a" * 81),
        ({"city": "Delhi", "extra_field": "leaked_extra"}, "leaked_extra"),
        ({"city": "Delhi", "notes": "n" * 201}, "n" * 201),
        ({"city": "Delhi", "language": "fr_invalid"}, "fr_invalid"),
    ],
)
def test_api_advice_422_rejects_bad_input_without_echo(
    payload: dict[str, object],
    forbidden_echo: str | None,
) -> None:
    """Validation errors return 422 ErrorResponse and never echo raw user input."""
    client = TestClient(_app_with_fake(FakeAdviceService()))

    response = client.post("/api/v1/advice", json=payload)

    assert response.status_code == 422
    body = response.json()
    assert body["error_code"] == "validation_error"
    assert body["field_errors"]
    if forbidden_echo is not None:
        assert forbidden_echo not in response.text


def test_api_aqi_422_rejects_city_with_digits_without_echo() -> None:
    """GET /api/v1/aqi applies the same CityName validation and never echoes input."""
    client = TestClient(_app_with_fake(FakeAdviceService()))

    response = client.get("/api/v1/aqi", params={"city": "Mumbai99"})

    assert response.status_code == 422
    assert response.json()["error_code"] == "validation_error"
    assert "Mumbai99" not in response.text


def test_api_geocoding_error_maps_to_404() -> None:
    """GeocodingError from the service maps to HTTP 404."""
    fake = FakeAdviceService(error_to_raise=GeocodingError("City could not be found."))
    client = TestClient(_app_with_fake(fake))

    response = client.post("/api/v1/advice", json={"city": "Atlantis"})

    assert response.status_code == 404
    body = response.json()
    assert body["error_code"] == "geocoding_failed"
    assert body["message"] == "City could not be found."


def test_api_air_quality_unavailable_maps_to_503() -> None:
    """AirQualityUnavailableError maps to HTTP 503."""
    fake = FakeAdviceService(
        error_to_raise=AirQualityUnavailableError("Air quality data is currently unavailable.")
    )
    client = TestClient(_app_with_fake(fake))

    response = client.get("/api/v1/aqi", params={"city": "Delhi"})

    assert response.status_code == 503
    assert response.json()["error_code"] == "air_quality_unavailable"


def test_api_llm_error_maps_to_502_with_safe_message() -> None:
    """LLMError maps to 502 and never exposes internal provider details."""
    fake = FakeAdviceService(error_to_raise=LLMError("secret upstream bearer token failure"))
    client = TestClient(_app_with_fake(fake))

    response = client.post("/api/v1/advice", json={"city": "Delhi"})

    assert response.status_code == 502
    assert response.json()["error_code"] == "llm_error"
    assert "secret upstream" not in response.text


def test_api_unexpected_exception_returns_500_without_stack_trace(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Unhandled exceptions return a generic 500 and log only the exception type name."""
    fake = FakeAdviceService(error_to_raise=RuntimeError("sensitive_internal_detail"))
    client = TestClient(_app_with_fake(fake), raise_server_exceptions=False)

    with caplog.at_level(logging.ERROR):
        response = client.post("/api/v1/advice", json={"city": "Delhi"})

    assert response.status_code == 500
    body = response.json()
    assert body["error_code"] == "internal_error"
    assert "Traceback" not in response.text
    assert "sensitive_internal_detail" not in response.text
    assert "RuntimeError" in caplog.text
    assert "sensitive_internal_detail" not in caplog.text


def test_api_unconfigured_service_returns_503(client: TestClient) -> None:
    """Calling advice or aqi without a configured AdviceService returns 503 ErrorResponse."""
    response = client.post("/api/v1/advice", json={"city": "Delhi"})

    assert response.status_code == 503
    body = response.json()
    assert body["error_code"] == "service_unavailable"
    assert body["message"] == "Advice service is not configured"


def test_api_openapi_documents_schemas_and_error_responses(client: TestClient) -> None:
    """OpenAPI schema exposes AdviceResponse, AirSummaryResponse, and error responses."""
    openapi = client.get("/openapi.json").json()
    advice_post = openapi["paths"]["/api/v1/advice"]["post"]
    for code in ("200", "404", "422", "503"):
        assert code in advice_post["responses"]
    schemas = openapi["components"]["schemas"]
    assert "AdviceRequest" in schemas
    assert "AdviceResponse" in schemas
    assert "AirSummaryResponse" in schemas
    assert "ErrorResponse" in schemas


def test_api_static_root_serves_html_and_hides_docs_in_prod() -> None:
    """Root serves index.html via FileResponse; /docs is disabled in production."""
    dev_client = TestClient(create_app(settings=Settings(app_env="development")))
    assert dev_client.get("/").status_code == 200
    assert "text/html" in dev_client.get("/").headers["content-type"]
    assert dev_client.get("/docs").status_code == 200
    assert dev_client.get("/static/styles.css").status_code == 200

    prod_client = TestClient(create_app(settings=Settings(app_env="production")))
    assert prod_client.get("/docs").status_code == 404
