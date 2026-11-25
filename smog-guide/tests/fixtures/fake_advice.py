"""Deterministic fake AdviceService for API integration tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from smogguide.domain.aqi import build_air_summary
from smogguide.domain.models import (
    AdviceResult,
    AirQuality,
    AirSummary,
    Applicability,
    CostTier,
    ExposureRange,
    HourlyReading,
    HouseholdProfile,
    Impact,
    Language,
    PlanImpact,
    Recommendation,
    RecommendationCategory,
)


def make_sample_air_summary(city: str = "Delhi") -> AirSummary:
    """Build a deterministic AirSummary fixture for tests."""
    base = datetime(2026, 11, 25, 8, 0, tzinfo=UTC)
    forecast = (
        HourlyReading(time=base, pm25=220.0),
        HourlyReading(time=base + timedelta(hours=1), pm25=160.0),
        HourlyReading(time=base + timedelta(hours=2), pm25=140.0),
    )
    air = AirQuality(
        pm25=210.0,
        pm10=310.0,
        us_aqi=260,
        observed_at=base,
        location_name=city,
        latitude=28.6139,
        longitude=77.2090,
        hourly_pm25_forecast=forecast,
    )
    return build_air_summary(air)


def make_sample_advice_result(city: str = "Delhi") -> AdviceResult:
    """Build a deterministic AdviceResult fixture for tests."""
    rec_routine = Recommendation(
        id="shift_walk_cleanest_window",
        category=RecommendationCategory.ROUTINE,
        title="Move outdoor errands to midday",
        action="Go outdoors during the lower-PM2.5 midday window instead of early morning.",
        cost_tier=CostTier.FREE,
        priority=10,
        impact=Impact(
            summary="Lowers short-term outdoor PM2.5 inhalation",
            estimate="roughly 15-35% lower peak exposure",
            assumptions=("Assumes typical winter morning inversion",),
            source="general guidance",
        ),
        applicability=Applicability(),
    )
    rec_indoor = Recommendation(
        id="wet_mopping_daily",
        category=RecommendationCategory.INDOOR,
        title="Wet-mop floors instead of dry sweeping",
        action="Use a damp cloth or mop so settled dust does not become airborne again.",
        cost_tier=CostTier.FREE,
        priority=15,
        impact=Impact(
            summary="Prevents resuspension of settled indoor particles",
            estimate="roughly 10-25% lower indoor coarse dust",
            assumptions=("Assumes tiled or concrete flooring",),
            source="general guidance",
        ),
        applicability=Applicability(),
    )
    rec_alt = Recommendation(
        id="avoid_open_waste_burning",
        category=RecommendationCategory.ALTERNATIVE,
        title="Avoid burning leaves or trash",
        action="Compost or hand over garden waste to municipal collection.",
        cost_tier=CostTier.FREE,
        priority=20,
        impact=Impact(
            summary="Eliminates localized smoke spikes near the home",
            estimate="prevents short spikes over 400 ug/m3 nearby",
            assumptions=("Assumes waste collection or composting space is available",),
            source="general guidance",
        ),
        applicability=Applicability(),
    )
    return AdviceResult(
        air_summary=make_sample_air_summary(city=city),
        routine=(rec_routine,),
        indoor=(rec_indoor,),
        alternatives=(rec_alt,),
        friendly_summary="Air quality is Very Poor today. Keep outdoor errands short and midday.",
        plan_impact=PlanImpact(
            exposure_without_plan=ExposureRange(low=180.0, high=240.0),
            exposure_with_plan=ExposureRange(low=100.0, high=150.0),
            assumptions=("Assumes windows are closed during peak morning smog",),
        ),
        disclaimer="General air quality guidance only; not medical advice.",
        generated_by="rules",
    )


class FakeAdviceService:
    """Deterministic fake satisfying the AdviceService Protocol for tests."""

    def __init__(self, error_to_raise: Exception | None = None) -> None:
        self.error_to_raise = error_to_raise
        self.last_advice_args: tuple[str, HouseholdProfile, Language, str | None] | None = None
        self.last_aqi_city: str | None = None

    async def get_advice(
        self,
        city: str,
        profile: HouseholdProfile,
        language: Language,
        notes: str | None,
    ) -> AdviceResult:
        """Record call arguments and either raise configured error or return fixture."""
        self.last_advice_args = (city, profile, language, notes)
        if self.error_to_raise is not None:
            raise self.error_to_raise
        return make_sample_advice_result(city=city)

    async def get_air_summary(self, city: str) -> AirSummary:
        """Record city argument and either raise configured error or return fixture."""
        self.last_aqi_city = city
        if self.error_to_raise is not None:
            raise self.error_to_raise
        return make_sample_air_summary(city=city)
