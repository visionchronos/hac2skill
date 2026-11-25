"""AQI classification using the CPCB (India) National AQI PM2.5 breakpoints.

Pure domain logic with no I/O.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from datetime import timedelta
from types import MappingProxyType

from pydantic import BaseModel, ConfigDict

from smogguide.domain.models import AirQuality, AirSummary, HourlyReading, RiskLevel, TimeWindow
from smogguide.utils.errors import InvalidInputError

# Source: Central Pollution Control Board (CPCB), India — National Air Quality Index
# (NAQI) technical documentation (Control of Urban Pollution Series: CUPS/82/2014-15),
# 24-hour average PM2.5 health breakpoint concentrations in ug/m3:
#   0-30 Good, 31-60 Satisfactory, 61-90 Moderately Polluted,
#   91-120 Poor, 121-250 Very Poor, >250 Severe.
#
# Known limitation: CPCB breakpoints are defined for 24-hour averages, whereas our
# air quality provider supplies instantaneous/hourly readings. Categories computed
# here are therefore indicative for immediate guidance rather than regulatory 24h status.
PM25_BANDS: tuple[tuple[float, RiskLevel], ...] = (
    (30.0, RiskLevel.GOOD),
    (60.0, RiskLevel.SATISFACTORY),
    (90.0, RiskLevel.MODERATE),
    (120.0, RiskLevel.POOR),
    (250.0, RiskLevel.VERY_POOR),
)

_ONE_HOUR = timedelta(hours=1)


class RiskInfo(BaseModel):
    """Human-readable display metadata for a single RiskLevel."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    label: str
    plain_meaning: str
    icon_name: str


RISK_INFO: Mapping[RiskLevel, RiskInfo] = MappingProxyType(
    {
        RiskLevel.GOOD: RiskInfo(
            label="Good",
            plain_meaning="The air is clean and safe for everyone to spend time outdoors.",
            icon_name="check-circle",
        ),
        RiskLevel.SATISFACTORY: RiskInfo(
            label="Satisfactory",
            plain_meaning=(
                "Air quality is acceptable, though very sensitive people may feel mild discomfort."
            ),
            icon_name="smile",
        ),
        RiskLevel.MODERATE: RiskInfo(
            label="Moderate",
            plain_meaning=(
                "Children, older adults, and people with asthma or heart issues "
                "may feel breathing discomfort."
            ),
            icon_name="alert-circle",
        ),
        RiskLevel.POOR: RiskInfo(
            label="Poor",
            plain_meaning=(
                "Long time outdoors can cause breathing discomfort for most people "
                "and affect sensitive groups."
            ),
            icon_name="alert-triangle",
        ),
        RiskLevel.VERY_POOR: RiskInfo(
            label="Very Poor",
            plain_meaning=(
                "Spending time outside may cause breathing illness, especially for "
                "children, older adults, and people with lung or heart conditions."
            ),
            icon_name="shield-alert",
        ),
        RiskLevel.SEVERE: RiskInfo(
            label="Severe",
            plain_meaning=(
                "The air is unhealthy even for healthy people and can seriously "
                "harm anyone with lung or heart conditions."
            ),
            icon_name="octagon-alert",
        ),
    }
)


def risk_from_pm25(pm25: float) -> RiskLevel:
    """Classify an instantaneous PM2.5 reading (ug/m3) onto the CPCB scale.

    Args:
        pm25: PM2.5 concentration in micrograms per cubic metre.

    Raises:
        InvalidInputError: If ``pm25`` is negative, NaN, or infinite.
    """
    if math.isnan(pm25) or math.isinf(pm25) or pm25 < 0.0:
        raise InvalidInputError("PM2.5 concentration must be a finite, non-negative number.")

    for upper_bound, risk_level in PM25_BANDS:
        if pm25 <= upper_bound:
            return risk_level
    return RiskLevel.SEVERE


def _is_consecutive_hourly(readings: Sequence[HourlyReading]) -> bool:
    """Return True when each adjacent reading is separated by exactly one hour."""
    return all(
        readings[i + 1].time - readings[i].time == _ONE_HOUR for i in range(len(readings) - 1)
    )


def find_cleanest_window(
    forecast: Sequence[HourlyReading],
    hours: int = 2,
) -> TimeWindow | None:
    """Return the contiguous hourly window with the lowest mean PM2.5.

    Ties resolve to the earliest chronological window. A time gap other than
    one hour breaks a candidate window.

    Args:
        forecast: Sequence of hourly PM2.5 readings.
        hours: Number of consecutive hours in the window (default 2).

    Raises:
        InvalidInputError: If ``hours`` is less than 1.
    """
    if hours < 1:
        raise InvalidInputError("Cleanest window duration must be at least 1 hour.")
    if len(forecast) < hours:
        return None

    ordered = sorted(forecast, key=lambda reading: reading.time)
    best_window: TimeWindow | None = None

    for start_idx in range(len(ordered) - hours + 1):
        chunk = ordered[start_idx : start_idx + hours]
        if not _is_consecutive_hourly(chunk):
            continue
        mean_pm25 = sum(reading.pm25 for reading in chunk) / hours
        # Strict '<' ensures ties resolve to the earliest chronological window.
        if best_window is None or mean_pm25 < best_window.mean_pm25:
            best_window = TimeWindow(
                start=chunk[0].time,
                end=chunk[-1].time + _ONE_HOUR,
                mean_pm25=mean_pm25,
            )

    return best_window


def build_air_summary(air: AirQuality) -> AirSummary:
    """Classify current air quality and locate the cleanest forecast window."""
    return AirSummary(
        air=air,
        risk_level=risk_from_pm25(air.pm25),
        cleanest_window=find_cleanest_window(air.hourly_pm25_forecast),
    )
