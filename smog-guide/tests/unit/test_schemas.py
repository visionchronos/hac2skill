"""Unit tests for API request schemas, normalization, and response mappers."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from smogguide.api.schemas import (
    AdviceRequest,
    to_advice_response,
    to_air_response,
)
from smogguide.domain.aqi import RISK_INFO
from smogguide.domain.models import (
    AdviceResult,
    AirQuality,
    AirSummary,
    ExposureRange,
    PlanImpact,
    RiskLevel,
)


@pytest.mark.parametrize(
    ("raw_city", "expected_city"),
    [
        ("Delhi", "Delhi"),
        ("  New   Delhi  ", "New Delhi"),
        ("नई   दिल्ली", "नई दिल्ली"),
        ("मुंबई", "मुंबई"),
        ("St. John's, O’Connor-East", "St. John's, O’Connor-East"),
    ],
)
def test_schemas_city_normalization_and_unicode_accepted(
    raw_city: str,
    expected_city: str,
) -> None:
    """Valid city names collapse whitespace and accept Unicode including Devanagari."""
    req = AdviceRequest(city=raw_city)
    assert req.city == expected_city


@pytest.mark.parametrize(
    "bad_city",
    [
        "",
        "   ",
        "Delhi123",
        "Delhi@Home",
        "Delhi\x00",
        "New\nDelhi",
        "...",
        "a" * 81,
    ],
)
def test_schemas_invalid_city_rejected(bad_city: str) -> None:
    """Empty, over-long, digit-containing, symbol, or control-char cities fail."""
    with pytest.raises(ValidationError):
        AdviceRequest(city=bad_city)


def test_schemas_notes_normalized_and_control_chars_rejected() -> None:
    """Blank notes become None, outer whitespace strips, and control chars raise."""
    assert AdviceRequest(city="Delhi", notes=None).notes is None
    assert AdviceRequest(city="Delhi", notes="   ").notes is None
    assert AdviceRequest(city="Delhi", notes="  no purifier  ").notes == "no purifier"

    with pytest.raises(ValidationError):
        AdviceRequest(city="Delhi", notes="hello\x00world")
    with pytest.raises(ValidationError):
        AdviceRequest(city="Delhi", notes="line1\nline2")
    with pytest.raises(ValidationError):
        AdviceRequest(city="Delhi", notes="x" * 201)


@pytest.mark.parametrize("risk_level", list(RiskLevel))
def test_schemas_mappers_populate_risk_info_for_every_level(risk_level: RiskLevel) -> None:
    """to_air_response and to_advice_response map RISK_INFO fields for every RiskLevel."""
    air = AirQuality(
        pm25=75.0,
        observed_at=datetime(2026, 11, 25, 10, 0, tzinfo=UTC),
        location_name="Kanpur",
        latitude=26.4499,
        longitude=80.3319,
    )
    summary = AirSummary(air=air, risk_level=risk_level, cleanest_window=None)
    result = AdviceResult(
        air_summary=summary,
        routine=(),
        indoor=(),
        alternatives=(),
        friendly_summary="Summary text.",
        plan_impact=PlanImpact(
            exposure_without_plan=ExposureRange(low=60.0, high=90.0),
            exposure_with_plan=ExposureRange(low=40.0, high=60.0),
        ),
        disclaimer="Not medical advice.",
        generated_by="rules",
    )

    expected = RISK_INFO[risk_level]
    air_resp = to_air_response(summary)
    assert air_resp.risk_level is risk_level
    assert air_resp.risk_label == expected.label
    assert air_resp.plain_meaning == expected.plain_meaning
    assert air_resp.icon_name == expected.icon_name

    advice_resp = to_advice_response(result)
    assert advice_resp.risk.level is risk_level
    assert advice_resp.risk.label == expected.label
    assert advice_resp.risk.plain_meaning == expected.plain_meaning
    assert advice_resp.risk.icon_name == expected.icon_name
