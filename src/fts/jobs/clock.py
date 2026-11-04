"""Injectable clocks so lease expiry tests do not sleep."""

from __future__ import annotations

import time
from typing import Protocol


class Clock(Protocol):
    def now(self) -> float:
        """Monotonic-enough seconds. Tests use a fake; the demo uses one too."""


class SystemClock:
    def now(self) -> float:
        return time.time()


class FakeClock:
    def __init__(self, start: float = 1_700_000_000.0) -> None:
        self._now = start

    def now(self) -> float:
        return self._now

    def advance(self, seconds: float) -> None:
        if seconds < 0:
            raise ValueError("cannot move the fake clock backwards")
        self._now += seconds


class SequenceIds:
    """Deterministic ids for the scripted walkthrough and for tests."""

    def __init__(self) -> None:
        self._n = 0

    def __call__(self, kind: str) -> str:
        self._n += 1
        return f"{kind}-{self._n:04d}"
