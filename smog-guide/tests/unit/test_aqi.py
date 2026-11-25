"""Unit tests for CPCB PM2.5 risk classification and cleanest window finder."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from smogguide.domain.aqi import (
    RISK_INFO,
    build_air_summary,
    find_cleanest_window,
    risk_from_pm25,
)
from smogguide.domain.models import AirQuality, HourlyReading, RiskLevel
from smogguide.utils.errors import InvalidInputError


def _reading(hour_offset: int, pm25: float) -> HourlyReading:
    base = datetime(2026, 11, 25, 6, 0, tzinfo=UTC)
    return HourlyReading(time=base + timedelta(hours=hour_offset), pm25=pm25)


@pytest.mark.parametrize(
    ("pm25", "expected"),
    [
        (0.0, RiskLevel.GOOD),
        (30.0, RiskLevel.GOOD),
        (30.1, RiskLevel.SATISFACTORY),
        (60.0, RiskLevel.SATISFACTORY),
        (60.1, RiskLevel.MODERATE),
        (90.0, RiskLevel.MODERATE),
        (90.1, RiskLevel.POOR),
        (120.0, RiskLevel.POOR),
        (120.1, RiskLevel.VERY_POOR),
        (250.0, RiskLevel.VERY_POOR),
        (250.1, RiskLevel.SEVERE),
        (999.0, RiskLevel.SEVERE),
    ],
)
def test_aqi_risk_from_pm25_cpcb_boundaries(pm25: float, expected: RiskLevel) -> None:
    """Every CPCB breakpoint upper bound and step above must map accurately."""
    assert risk_from_pm25(pm25) is expected


@pytest.mark.parametrize("bad_pm25", [-0.01, -100.0, float("nan"), float("inf"), float("-inf")])
def test_aqi_risk_from_pm25_invalid_input_raises(bad_pm25: float) -> None:
    """Negative, NaN, and infinite PM2.5 inputs must raise InvalidInputError."""
    with pytest.raises(InvalidInputError):
        risk_from_pm25(bad_pm25)


def test_aqi_risk_info_covers_every_risk_level() -> None:
    """Every RiskLevel enum member must have a populated RISK_INFO entry."""
    assert set(RISK_INFO.keys()) == set(RiskLevel)
    for level in RiskLevel:
        info = RISK_INFO[level]
        assert info.label
        assert info.plain_meaning
        assert info.icon_name


def test_aqi_find_cleanest_window_normal_forecast() -> None:
    """Returns the contiguous window with the lowest mean PM2.5."""
    forecast = [
        _reading(0, 180.0),
        _reading(1, 140.0),
        _reading(2, 70.0),
        _reading(3, 90.0),
        _reading(4, 150.0),
    ]
    window = find_cleanest_window(forecast, hours=2)
    assert window is not None
    assert window.start == _reading(2, 0.0).time
    assert window.end == _reading(4, 0.0).time
    assert window.mean_pm25 == pytest.approx(80.0)


def test_aqi_find_cleanest_window_tie_resolves_earliest() -> None:
    """Equal mean PM2.5 windows must resolve to the earliest window."""
    forecast = [
        _reading(0, 60.0),
        _reading(1, 60.0),
        _reading(2, 120.0),
        _reading(3, 60.0),
        _reading(4, 60.0),
    ]
    window = find_cleanest_window(forecast, hours=2)
    assert window is not None
    assert window.start == _reading(0, 0.0).time
    assert window.end == _reading(2, 0.0).time


def test_aqi_find_cleanest_window_empty_or_short_returns_none() -> None:
    """Empty forecasts or forecasts shorter than requested hours return None."""
    assert find_cleanest_window([], hours=2) is None
    assert find_cleanest_window([_reading(0, 50.0)], hours=2) is None


def test_aqi_find_cleanest_window_gap_breaks_window() -> None:
    """Non-consecutive hours must not form a valid window."""
    # Gap between hour 1 and hour 3 means only hours (3, 4) are consecutive.
    forecast = [
        _reading(0, 20.0),
        _reading(1, 20.0),
        _reading(3, 100.0),
        _reading(4, 110.0),
    ]
    # Remove hour 1 so (0, 3) is separated by a gap, leaving only (3, 4).
    gapped = [forecast[0], forecast[2], forecast[3]]
    window = find_cleanest_window(gapped, hours=2)
    assert window is not None
    assert window.start == _reading(3, 0.0).time
    assert window.end == _reading(5, 0.0).time
    assert window.mean_pm25 == pytest.approx(105.0)


def test_aqi_find_cleanest_window_all_gapped_returns_none() -> None:
    """Forecast with no consecutive pairs returns None."""
    gapped = [_reading(0, 20.0), _reading(2, 30.0), _reading(5, 40.0)]
    assert find_cleanest_window(gapped, hours=2) is None


def test_aqi_find_cleanest_window_invalid_hours_raises() -> None:
    """Window length below 1 hour must raise InvalidInputError."""
    with pytest.raises(InvalidInputError):
        find_cleanest_window([_reading(0, 40.0)], hours=0)


def test_aqi_build_air_summary_combines_risk_and_window() -> None:
    """build_air_summary computes both risk_level and cleanest_window."""
    forecast = (_reading(0, 150.0), _reading(1, 80.0), _reading(2, 60.0))
    air = AirQuality(
        pm25=110.0,
        observed_at=_reading(0, 110.0).time,
        location_name="Delhi",
        latitude=28.6139,
        longitude=77.2090,
        hourly_pm25_forecast=forecast,
    )
    summary = build_air_summary(air)
    assert summary.air is air
    assert summary.risk_level is RiskLevel.POOR
    assert summary.cleanest_window is not None
    assert summary.cleanest_window.mean_pm25 == pytest.approx(70.0)
