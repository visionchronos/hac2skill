"""Protocol interface for the advice orchestration service."""

from __future__ import annotations

from typing import Protocol

from smogguide.domain.models import AdviceResult, AirSummary, HouseholdProfile, Language


class AdviceService(Protocol):
    """Contract that advice orchestration services must satisfy."""

    async def get_advice(
        self,
        city: str,
        profile: HouseholdProfile,
        language: Language,
        notes: str | None,
    ) -> AdviceResult:
        """Return personalized air-pollution guidance for a city and household."""
        ...

    async def get_air_summary(self, city: str) -> AirSummary:
        """Return current air quality classification and cleanest forecast window."""
        ...
