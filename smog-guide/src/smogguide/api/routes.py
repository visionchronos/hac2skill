"""FastAPI route definitions for SmogGuide.

Contains only HTTP routing, validation, delegation to AdviceService, and
response mapping. Business logic lives exclusively in domain/ and services/.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, status

from smogguide import __version__
from smogguide.api.dependencies import get_advice_service
from smogguide.api.schemas import (
    AdviceRequest,
    AdviceResponse,
    AirSummaryResponse,
    CityName,
    ErrorResponse,
    HealthResponse,
    to_advice_response,
    to_air_response,
)
from smogguide.services.advice_service import AdviceService

router = APIRouter()

_ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    status.HTTP_404_NOT_FOUND: {
        "model": ErrorResponse,
        "description": "Location could not be found.",
    },
    status.HTTP_422_UNPROCESSABLE_CONTENT: {
        "model": ErrorResponse,
        "description": "Request validation failed.",
    },
    status.HTTP_503_SERVICE_UNAVAILABLE: {
        "model": ErrorResponse,
        "description": "Air quality data or advice service is temporarily unavailable.",
    },
}


@router.get(
    "/health",
    tags=["ops"],
    summary="Service health check",
    description="Return service liveness status and the running application version.",
    response_model=HealthResponse,
)
async def health_check() -> HealthResponse:
    """Return service liveness status and current version."""
    return HealthResponse(status="ok", version=__version__)


@router.post(
    "/api/v1/advice",
    tags=["advice"],
    summary="Get personalized air-pollution advice",
    description=(
        "Classify local air quality and return deterministic, profile-aware "
        "recommendations with estimated impact ranges."
    ),
    response_model=AdviceResponse,
    responses=_ERROR_RESPONSES,
)
async def create_advice(
    payload: AdviceRequest,
    service: Annotated[AdviceService, Depends(get_advice_service)],
) -> AdviceResponse:
    """Generate personalized air-pollution guidance for a city and household."""
    result = await service.get_advice(
        city=payload.city,
        profile=payload.profile,
        language=payload.language,
        notes=payload.notes,
    )
    return to_advice_response(result)


@router.get(
    "/api/v1/aqi",
    tags=["aqi"],
    summary="Get current air quality summary",
    description="Look up current PM2.5, CPCB risk category, and cleanest forecast window.",
    response_model=AirSummaryResponse,
    responses=_ERROR_RESPONSES,
)
async def get_aqi_summary(
    city: Annotated[CityName, Query(description="City or locality name in India.")],
    service: Annotated[AdviceService, Depends(get_advice_service)],
) -> AirSummaryResponse:
    """Return current CPCB risk classification and cleanest forecast window."""
    summary = await service.get_air_summary(city=city)
    return to_air_response(summary)
