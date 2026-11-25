"""Unit tests for immutable domain models, enums, and validators."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from smogguide.domain.models import (
    AirQuality,
    Applicability,
    CommuteMode,
    CookingFuel,
    CostTier,
    ExposureRange,
    HomeType,
    HourlyReading,
    HouseholdProfile,
    Impact,
    ProfileFlag,
    Recommendation,
    RecommendationCategory,
    RiskLevel,
    TimeWindow,
)


def _utc(hour: int = 10) -> datetime:
    return datetime(2026, 11, 25, hour, 0, tzinfo=UTC)


def test_models_risk_level_ordering_follows_severity() -> None:
    """OrderedStrEnum members must compare by definition order, not alphabetically."""
    assert RiskLevel.GOOD < RiskLevel.SATISFACTORY
    assert RiskLevel.SATISFACTORY < RiskLevel.MODERATE
    assert RiskLevel.MODERATE < RiskLevel.POOR
    assert RiskLevel.POOR >= RiskLevel.MODERATE
    assert RiskLevel.SEVERE > RiskLevel.VERY_POOR
    # Alphabetically "good" > "severe" would be wrong; definition order puts GOOD < SEVERE.
    assert RiskLevel.GOOD < RiskLevel.SEVERE
    assert RiskLevel.POOR.value == "poor"


def test_models_cost_tier_comparison_supports_budget_checks() -> None:
    """CostTier ordering must allow direct cost <= budget comparisons."""
    assert CostTier.FREE < CostTier.LOW < CostTier.MEDIUM
    assert CostTier.FREE <= CostTier.LOW
    assert CostTier.LOW <= CostTier.LOW
    assert not (CostTier.MEDIUM <= CostTier.LOW)


def test_models_enum_comparison_across_types_raises_type_error() -> None:
    """Comparing different OrderedStrEnum types must not fall back to string order."""
    with pytest.raises(TypeError):
        _ = RiskLevel.GOOD < CostTier.FREE  # type: ignore[operator]
    with pytest.raises(TypeError):
        _ = RiskLevel.GOOD <= CostTier.FREE  # type: ignore[operator]
    with pytest.raises(TypeError):
        _ = RiskLevel.GOOD > CostTier.FREE  # type: ignore[operator]
    with pytest.raises(TypeError):
        _ = RiskLevel.GOOD >= CostTier.FREE  # type: ignore[operator]


def test_models_naive_datetime_is_rejected() -> None:
    """Naive datetimes must be rejected on HourlyReading, AirQuality, and TimeWindow."""
    naive = datetime(2026, 11, 25, 10, 0)
    with pytest.raises(ValidationError):
        HourlyReading(time=naive, pm25=45.0)
    with pytest.raises(ValidationError):
        AirQuality(
            pm25=45.0,
            observed_at=naive,
            location_name="Delhi",
            latitude=28.6,
            longitude=77.2,
        )


def test_models_negative_pm25_is_rejected() -> None:
    """Negative PM2.5 values must fail validation."""
    with pytest.raises(ValidationError):
        HourlyReading(time=_utc(), pm25=-0.1)
    with pytest.raises(ValidationError):
        AirQuality(
            pm25=-5.0,
            observed_at=_utc(),
            location_name="Delhi",
            latitude=28.6,
            longitude=77.2,
        )


def test_models_extra_field_is_rejected() -> None:
    """Unknown fields must be forbidden on all domain models."""
    with pytest.raises(ValidationError):
        HouseholdProfile(unexpected_field=True)  # type: ignore[call-arg]
    with pytest.raises(ValidationError):
        Impact(summary="Reduces exposure", extra_key="nope")  # type: ignore[call-arg]


def test_models_frozen_instance_rejects_mutation() -> None:
    """Frozen models must raise ValidationError when mutated."""
    profile = HouseholdProfile()
    with pytest.raises(ValidationError):
        profile.has_children = True  # type: ignore[misc]


def test_models_time_window_requires_end_after_start() -> None:
    """TimeWindow must reject end <= start."""
    with pytest.raises(ValidationError):
        TimeWindow(start=_utc(10), end=_utc(10), mean_pm25=50.0)
    with pytest.raises(ValidationError):
        TimeWindow(start=_utc(11), end=_utc(10), mean_pm25=50.0)
    valid = TimeWindow(start=_utc(10), end=_utc(12), mean_pm25=50.0)
    assert valid.end - valid.start == timedelta(hours=2)


def test_models_exposure_range_rejects_low_above_high() -> None:
    """ExposureRange must reject low > high."""
    with pytest.raises(ValidationError):
        ExposureRange(low=80.0, high=40.0)
    equal = ExposureRange(low=40.0, high=40.0)
    assert equal.unit == "ug/m3"


def test_models_applicability_rejects_min_above_max_risk() -> None:
    """Applicability must reject min_risk > max_risk."""
    with pytest.raises(ValidationError):
        Applicability(min_risk=RiskLevel.SEVERE, max_risk=RiskLevel.POOR)
    valid = Applicability(min_risk=RiskLevel.POOR, max_risk=RiskLevel.POOR)
    assert valid.min_risk == valid.max_risk


@pytest.mark.parametrize(
    ("flags", "expected"),
    [
        ({}, False),
        ({"has_air_purifier": True}, False),
        ({"has_children": True}, True),
        ({"has_elderly": True}, True),
        ({"has_respiratory_condition": True}, True),
        ({"is_pregnant": True}, True),
        ({"has_children": True, "has_elderly": True, "has_air_purifier": True}, True),
    ],
)
def test_models_household_has_vulnerable_member_truth_table(
    flags: dict[str, bool],
    expected: bool,
) -> None:
    """has_vulnerable_member must reflect the four health-vulnerability booleans only."""
    profile = HouseholdProfile(**flags)
    assert profile.has_vulnerable_member is expected


def test_models_household_profile_defaults_and_hashability() -> None:
    """HouseholdProfile defaults to LOW budget and is hashable for cache keys."""
    profile_a = HouseholdProfile()
    profile_b = HouseholdProfile(
        commute_mode=CommuteMode.WALK,
        cooking_fuel=CookingFuel.LPG,
        home_type=HomeType.APARTMENT,
        budget_tier=CostTier.LOW,
    )
    assert profile_a.budget_tier is CostTier.LOW
    assert hash(profile_a) == hash(profile_b)
    cache: dict[HouseholdProfile, str] = {profile_a: "cached"}
    assert cache[profile_b] == "cached"


def test_models_recommendation_validates_id_slug_and_bounds() -> None:
    """Recommendation enforces slug pattern on id and priority bounds."""
    impact = Impact(summary="Cuts indoor PM2.5", estimate="20-40%")
    applicability = Applicability(requires_flags=frozenset({ProfileFlag.HAS_CHILDREN}))
    rec = Recommendation(
        id="close_windows_morning",
        category=RecommendationCategory.INDOOR,
        title="Keep windows shut during peak smog",
        action="Close street-facing windows between 6 AM and 10 AM.",
        cost_tier=CostTier.FREE,
        priority=10,
        impact=impact,
        applicability=applicability,
    )
    assert rec.impact.source == "general guidance"

    with pytest.raises(ValidationError):
        Recommendation(
            id="Invalid-Slug!",
            category=RecommendationCategory.INDOOR,
            title="Test",
            action="Test action",
            cost_tier=CostTier.FREE,
            priority=10,
            impact=impact,
            applicability=applicability,
        )
