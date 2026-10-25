"""
Clock abstraction for deterministic time testing across scheduling, aging, leases, and backoff.
"""

import time
from typing import Optional

class Clock:
    def __init__(self, initial_time: Optional[float] = None):
        self._manual = initial_time is not None
        self._current_time = initial_time if initial_time is not None else time.time()

    def now(self) -> float:
        if self._manual:
            return self._current_time
        return time.time()

    def advance(self, seconds: float) -> None:
        if not self._manual:
            raise RuntimeError("Cannot advance a real-time clock manually; instantiate with initial_time.")
        self._current_time += seconds

    def set_time(self, timestamp: float) -> None:
        self._manual = True
        self._current_time = timestamp

    @property
    def is_manual(self) -> bool:
        return self._manual
