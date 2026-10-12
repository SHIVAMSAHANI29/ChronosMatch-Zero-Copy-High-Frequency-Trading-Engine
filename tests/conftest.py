"""Shared test helpers."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from src.matching_engine import MatchingEngine


class FakeClock:
    """Deterministic clock: each call advances by one millisecond."""

    def __init__(self) -> None:
        self._now = datetime(2026, 1, 1, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        self._now += timedelta(milliseconds=1)
        return self._now


@pytest.fixture
def engine() -> MatchingEngine:
    return MatchingEngine(clock=FakeClock())
