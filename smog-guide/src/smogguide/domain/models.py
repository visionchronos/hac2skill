"""Frozen Pydantic v2 domain models and enums for SmogGuide.

Models are immutable data containers only; business logic belongs in
``domain/aqi.py``, ``domain/rules.py``, and ``domain/impact.py``.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

# Validation limits stored as named constants to avoid magic numbers.
_MAX_US_AQI = 500
_MIN_LATITUDE = -90.0
_MAX_LATITUDE = 90.0
_MIN_LONGITUDE = -180.0
_MAX_LONGITUDE = 180.0
_MAX_LOCATION_NAME_LEN = 120
_MAX_IMPACT_SUMMARY_LEN = 200
_MAX_RECOMMENDATION_ID_LEN = 60
_MAX_TITLE_LEN = 80
_MAX_ACTION_LEN = 300
_MIN_PRIORITY = 1
_MAX_PRIORITY = 100
_RECOMMENDATION_ID_PATTERN = r"^[a-z0-9_]+$"
_DEFAULT_PLAN_IMPACT_LABEL = "Estimate based on general research, not a medical prediction."


class OrderedStrEnum(StrEnum):
    """StrEnum whose members compare by definition order instead of text order."""

    def _order_index(self) -> int:
        return list(type(self)).index(self)

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, type(self)):
            return NotImplemented
        return self._order_index() < other._order_index()

    def __le__(self, other: object) -> bool:
        if not isinstance(other, type(self)):
            return NotImplemented
        return self._order_index() <= other._order_index()

    def __gt__(self, other: object) -> bool:
        if not isinstance(other, type(self)):
            return NotImplemented
        return self._order_index() > other._order_index()

    def __ge__(self, other: object) -> bool:
        if not isinstance(other, type(self)):
            return NotImplemented
        return self._order_index() >= other._order_index()


class RiskLevel(OrderedStrEnum):
    """CPCB National Air Quality Index risk categories in ascending severity."""

    GOOD = "good"
    SATISFACTORY = "satisfactory"
    MODERATE = "moderate"
    POOR = "poor"
    VERY_POOR = "very_poor"
    SEVERE = "severe"


class CostTier(OrderedStrEnum):
    """Cost level for a recommendation or a household's budget ceiling."""

    FREE = "free"
    LOW = "low"
    MEDIUM = "medium"


class CommuteMode(StrEnum):
    """Primary outdoor commute mode for a household member."""

    WALK = "walk"
    BIKE = "bike"
    BUS = "bus"
    CAR = "car"
    TWO_WHEELER = "two_wheeler"


class CookingFuel(StrEnum):
    """Primary household cooking fuel source."""

    LPG = "lpg"
    INDUCTION = "induction"
    BIOMASS = "biomass"
    OTHER = "other"


class HomeType(StrEnum):
    """Dwelling type affecting ventilation and indoor air strategies."""

    APARTMENT = "apartment"
    HOUSE = "house"


class RecommendationCategory(StrEnum):
    """Domain grouping for generated advice items."""

    ROUTINE = "routine"
    INDOOR = "indoor"
    ALTERNATIVE = "alternative"


class Language(StrEnum):
    """Supported output languages for user-facing text."""

    EN = "en"
    HI = "hi"
    OR = "or"


class ProfileFlag(StrEnum):
    """Typed identifiers for boolean HouseholdProfile attributes."""

    HAS_CHILDREN = "has_children"
    HAS_ELDERLY = "has_elderly"
    HAS_RESPIRATORY_CONDITION = "has_respiratory_condition"
    IS_PREGNANT = "is_pregnant"
    HAS_AIR_PURIFIER = "has_air_purifier"


class _DomainModel(BaseModel):
    """Base configuration shared by all immutable domain models."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        allow_inf_nan=False,
    )


class HourlyReading(_DomainModel):
    """Single hourly PM2.5 forecast or observation point."""

    time: AwareDatetime
    pm25: float = Field(ge=0.0)


class AirQuality(_DomainModel):
    """Observed air quality and optional hourly PM2.5 forecast for a location."""

    pm25: float = Field(ge=0.0)
    pm10: float | None = Field(default=None, ge=0.0)
    us_aqi: int | None = Field(default=None, ge=0, le=_MAX_US_AQI)
    observed_at: AwareDatetime
    location_name: str = Field(min_length=1, max_length=_MAX_LOCATION_NAME_LEN)
    latitude: float = Field(ge=_MIN_LATITUDE, le=_MAX_LATITUDE)
    longitude: float = Field(ge=_MIN_LONGITUDE, le=_MAX_LONGITUDE)
    hourly_pm25_forecast: tuple[HourlyReading, ...] = ()


class TimeWindow(_DomainModel):
    """Contiguous forecast interval with its mean PM2.5 concentration."""

    start: AwareDatetime
    end: AwareDatetime
    mean_pm25: float = Field(ge=0.0)

    @model_validator(mode="after")
    def validate_end_after_start(self) -> TimeWindow:
        """Ensure the window end strictly follows its start."""
        if self.end <= self.start:
            raise ValueError("TimeWindow end must be after start")
        return self


class AirSummary(_DomainModel):
    """Classified air quality snapshot paired with the cleanest forecast window."""

    air: AirQuality
    risk_level: RiskLevel
    cleanest_window: TimeWindow | None = None


class HouseholdProfile(_DomainModel):
    """In-memory household sensitivity profile; hashable for cache keys."""

    has_children: bool = False
    has_elderly: bool = False
    has_respiratory_condition: bool = False
    is_pregnant: bool = False
    has_air_purifier: bool = False
    commute_mode: CommuteMode = CommuteMode.WALK
    cooking_fuel: CookingFuel = CookingFuel.LPG
    home_type: HomeType = HomeType.APARTMENT
    budget_tier: CostTier = CostTier.LOW

    @property
    def has_vulnerable_member(self) -> bool:
        """Return True when any household member belongs to a higher-risk group."""
        return (
            self.has_children
            or self.has_elderly
            or self.has_respiratory_condition
            or self.is_pregnant
        )


class Impact(_DomainModel):
    """Direct impact explanation and assumptions for a single recommendation."""

    summary: str = Field(min_length=1, max_length=_MAX_IMPACT_SUMMARY_LEN)
    estimate: str | None = None
    assumptions: tuple[str, ...] = ()
    source: str = "general guidance"


class Applicability(_DomainModel):
    """Matching rules determining when a recommendation applies to a household."""

    min_risk: RiskLevel = RiskLevel.GOOD
    max_risk: RiskLevel = RiskLevel.SEVERE
    requires_flags: frozenset[ProfileFlag] = frozenset()
    excludes_flags: frozenset[ProfileFlag] = frozenset()
    cooking_fuels: frozenset[CookingFuel] = frozenset()
    commute_modes: frozenset[CommuteMode] = frozenset()
    home_types: frozenset[HomeType] = frozenset()

    @model_validator(mode="after")
    def validate_risk_bounds(self) -> Applicability:
        """Ensure min_risk does not exceed max_risk."""
        if self.min_risk > self.max_risk:
            raise ValueError("Applicability min_risk must not exceed max_risk")
        return self


class Recommendation(_DomainModel):
    """A single actionable, rule-selected recommendation from the catalog."""

    id: str = Field(
        min_length=1,
        max_length=_MAX_RECOMMENDATION_ID_LEN,
        pattern=_RECOMMENDATION_ID_PATTERN,
    )
    category: RecommendationCategory
    title: str = Field(min_length=1, max_length=_MAX_TITLE_LEN)
    action: str = Field(min_length=1, max_length=_MAX_ACTION_LEN)
    cost_tier: CostTier
    priority: int = Field(ge=_MIN_PRIORITY, le=_MAX_PRIORITY)
    impact: Impact
    applicability: Applicability


class ExposureRange(_DomainModel):
    """Estimated PM2.5 exposure range (low to high)."""

    low: float = Field(ge=0.0)
    high: float = Field(ge=0.0)
    unit: str = "ug/m3"

    @model_validator(mode="after")
    def validate_low_not_above_high(self) -> ExposureRange:
        """Ensure the lower bound never exceeds the upper bound."""
        if self.low > self.high:
            raise ValueError("ExposureRange low must not exceed high")
        return self


class PlanImpact(_DomainModel):
    """Estimated exposure comparison with and without following the advice plan."""

    exposure_without_plan: ExposureRange
    exposure_with_plan: ExposureRange
    assumptions: tuple[str, ...] = ()
    label: str = _DEFAULT_PLAN_IMPACT_LABEL


class AdviceResult(_DomainModel):
    """Complete advice payload returned by the domain/service pipeline."""

    air_summary: AirSummary
    routine: tuple[Recommendation, ...]
    indoor: tuple[Recommendation, ...]
    alternatives: tuple[Recommendation, ...]
    friendly_summary: str
    plan_impact: PlanImpact
    disclaimer: str
    generated_by: Literal["rules", "llm"]
