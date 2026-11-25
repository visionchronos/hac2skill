"""Public API request/response schemas and domain-to-API mappers.

Keeps the HTTP contract decoupled from internal domain models while reusing
strict validation rules.
"""

from __future__ import annotations

import unicodedata
from typing import Annotated, Literal

from pydantic import AfterValidator, AwareDatetime, BaseModel, BeforeValidator, ConfigDict, Field

from smogguide.domain.aqi import RISK_INFO
from smogguide.domain.models import (
    AdviceResult,
    AirSummary,
    CostTier,
    HouseholdProfile,
    Language,
    Recommendation,
    RecommendationCategory,
    RiskLevel,
    TimeWindow,
)

_MIN_CITY_LEN = 1
_MAX_CITY_LEN = 80
_MAX_NOTES_LEN = 200
_ALLOWED_CITY_PUNCTUATION = frozenset({".", ",", "'", "’", "-"})
# Indic scripts (e.g., Devanagari, Odia) use combining marks (Mn/Mc) for vowel signs and virama.
_COMBINING_MARK_CATEGORIES = frozenset({"Mn", "Mc"})


def _has_control_char(text: str) -> bool:
    """Return True if any character belongs to a Unicode Control/Other-format category."""
    return any(unicodedata.category(ch).startswith("C") for ch in text)


def _normalize_city(raw: object) -> object:
    """Reject control characters and collapse whitespace in a city name."""
    if not isinstance(raw, str):
        return raw
    if _has_control_char(raw):
        raise ValueError("Invalid characters in city name.")
    return " ".join(raw.split())


def _validate_city_chars(city: str) -> str:
    """Validate that a normalized city contains only allowed Unicode characters."""
    has_letter = False
    for ch in city:
        category = unicodedata.category(ch)
        if category.startswith("L"):
            has_letter = True
        elif category in _COMBINING_MARK_CATEGORIES or ch == " " or ch in _ALLOWED_CITY_PUNCTUATION:
            continue
        else:
            raise ValueError("City name contains unsupported characters.")
    if not has_letter:
        raise ValueError("City name must contain at least one letter.")
    return city


def _normalize_and_validate_notes(raw: object) -> str | None:
    """Strip notes, convert blank strings to None, and reject control characters."""
    if raw is None:
        return None
    if not isinstance(raw, str):
        raise ValueError("Notes must be a string.")
    if _has_control_char(raw):
        raise ValueError("Notes contain unsupported characters.")
    stripped = raw.strip()
    if not stripped:
        return None
    if len(stripped) > _MAX_NOTES_LEN:
        raise ValueError("Notes exceed maximum length.")
    return stripped


CityName = Annotated[
    str,
    BeforeValidator(_normalize_city),
    Field(min_length=_MIN_CITY_LEN, max_length=_MAX_CITY_LEN),
    AfterValidator(_validate_city_chars),
]


class _RequestModel(BaseModel):
    """Base configuration for all incoming request models."""

    model_config = ConfigDict(extra="forbid")


class _ResponseModel(BaseModel):
    """Base configuration for all outgoing response models."""

    model_config = ConfigDict(frozen=True, extra="forbid")


class AdviceRequest(_RequestModel):
    """Request payload for personalized household air-pollution advice."""

    city: CityName
    profile: HouseholdProfile = Field(default_factory=HouseholdProfile)
    language: Language = Language.EN
    notes: Annotated[
        Annotated[str, Field(max_length=_MAX_NOTES_LEN)] | None,
        BeforeValidator(_normalize_and_validate_notes),
    ] = None


class HealthResponse(_ResponseModel):
    """Service liveness payload returned by GET /health."""

    status: str
    version: str


class TimeWindowResponse(_ResponseModel):
    """Serialized cleanest-air forecast window."""

    start: AwareDatetime
    end: AwareDatetime
    mean_pm25: float


class AirSummaryResponse(_ResponseModel):
    """Serialized current air quality summary for GET /api/v1/aqi."""

    location: str
    pm25: float
    pm10: float | None = None
    us_aqi: int | None = None
    risk_level: RiskLevel
    risk_label: str
    plain_meaning: str
    icon_name: str
    observed_at: AwareDatetime
    cleanest_window: TimeWindowResponse | None = None


class AirReadingResponse(_ResponseModel):
    """Air metrics portion of an AdviceResponse."""

    location: str
    pm25: float
    pm10: float | None = None
    us_aqi: int | None = None
    observed_at: AwareDatetime


class RiskSummaryResponse(_ResponseModel):
    """Classified risk level with plain-language meaning and icon identifier."""

    level: RiskLevel
    label: str
    plain_meaning: str
    icon_name: str


class ImpactResponse(_ResponseModel):
    """Serialized per-recommendation impact explanation."""

    summary: str
    estimate: str | None = None
    assumptions: tuple[str, ...]
    source: str


class RecommendationResponse(_ResponseModel):
    """Serialized recommendation item returned to clients."""

    id: str
    category: RecommendationCategory
    title: str
    action: str
    cost_tier: CostTier
    impact: ImpactResponse


class ExposureRangeResponse(_ResponseModel):
    """Serialized PM2.5 exposure range."""

    low: float
    high: float
    unit: str


class PlanImpactResponse(_ResponseModel):
    """Serialized comparison of estimated exposure with and without the plan."""

    exposure_without_plan: ExposureRangeResponse
    exposure_with_plan: ExposureRangeResponse
    assumptions: tuple[str, ...]
    label: str


class AdviceResponse(_ResponseModel):
    """Full personalized advice response for POST /api/v1/advice."""

    air: AirReadingResponse
    risk: RiskSummaryResponse
    cleanest_window: TimeWindowResponse | None = None
    routine: tuple[RecommendationResponse, ...]
    indoor: tuple[RecommendationResponse, ...]
    alternatives: tuple[RecommendationResponse, ...]
    friendly_summary: str
    plan_impact: PlanImpactResponse
    disclaimer: str
    generated_by: Literal["rules", "llm"]


class FieldError(_ResponseModel):
    """Single validation error entry without raw user input."""

    field: str
    message: str


class ErrorResponse(_ResponseModel):
    """Structured API error envelope; never echoes raw user input."""

    error_code: str
    message: str
    field_errors: list[FieldError] | None = None


def _to_time_window_response(window: TimeWindow | None) -> TimeWindowResponse | None:
    """Map an optional domain TimeWindow to its API schema."""
    if window is None:
        return None
    return TimeWindowResponse(
        start=window.start,
        end=window.end,
        mean_pm25=window.mean_pm25,
    )


def _to_recommendation_response(rec: Recommendation) -> RecommendationResponse:
    """Map a domain Recommendation to its public API representation."""
    return RecommendationResponse(
        id=rec.id,
        category=rec.category,
        title=rec.title,
        action=rec.action,
        cost_tier=rec.cost_tier,
        impact=ImpactResponse(
            summary=rec.impact.summary,
            estimate=rec.impact.estimate,
            assumptions=rec.impact.assumptions,
            source=rec.impact.source,
        ),
    )


def _to_plan_impact_response(result: AdviceResult) -> PlanImpactResponse:
    """Map domain PlanImpact to its API schema."""
    impact = result.plan_impact
    return PlanImpactResponse(
        exposure_without_plan=ExposureRangeResponse(
            low=impact.exposure_without_plan.low,
            high=impact.exposure_without_plan.high,
            unit=impact.exposure_without_plan.unit,
        ),
        exposure_with_plan=ExposureRangeResponse(
            low=impact.exposure_with_plan.low,
            high=impact.exposure_with_plan.high,
            unit=impact.exposure_with_plan.unit,
        ),
        assumptions=impact.assumptions,
        label=impact.label,
    )


def to_air_response(summary: AirSummary) -> AirSummaryResponse:
    """Map a domain AirSummary to an AirSummaryResponse using RISK_INFO."""
    info = RISK_INFO[summary.risk_level]
    air = summary.air
    return AirSummaryResponse(
        location=air.location_name,
        pm25=air.pm25,
        pm10=air.pm10,
        us_aqi=air.us_aqi,
        risk_level=summary.risk_level,
        risk_label=info.label,
        plain_meaning=info.plain_meaning,
        icon_name=info.icon_name,
        observed_at=air.observed_at,
        cleanest_window=_to_time_window_response(summary.cleanest_window),
    )


def to_advice_response(result: AdviceResult) -> AdviceResponse:
    """Map a domain AdviceResult to an AdviceResponse using RISK_INFO."""
    summary = result.air_summary
    air = summary.air
    info = RISK_INFO[summary.risk_level]
    return AdviceResponse(
        air=AirReadingResponse(
            location=air.location_name,
            pm25=air.pm25,
            pm10=air.pm10,
            us_aqi=air.us_aqi,
            observed_at=air.observed_at,
        ),
        risk=RiskSummaryResponse(
            level=summary.risk_level,
            label=info.label,
            plain_meaning=info.plain_meaning,
            icon_name=info.icon_name,
        ),
        cleanest_window=_to_time_window_response(summary.cleanest_window),
        routine=tuple(_to_recommendation_response(rec) for rec in result.routine),
        indoor=tuple(_to_recommendation_response(rec) for rec in result.indoor),
        alternatives=tuple(_to_recommendation_response(rec) for rec in result.alternatives),
        friendly_summary=result.friendly_summary,
        plan_impact=_to_plan_impact_response(result),
        disclaimer=result.disclaimer,
        generated_by=result.generated_by,
    )
