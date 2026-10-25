"""
Sliding Window Rate Limiter (SCH-130).
Enforces per-tenant and per-key request limits with HTTP 429 Retry-After.
"""

import time
from typing import Dict, List, Tuple, Optional


class SlidingWindowRateLimiter:
    """Sliding-window in-memory rate limiter per key/tenant."""

    def __init__(self, default_limit: int = 60, window_seconds: float = 60.0):
        self.default_limit = default_limit
        self.window_seconds = window_seconds
        # Maps key -> list of float timestamps
        self._history: Dict[str, List[float]] = {}
        # Custom limits per key
        self._custom_limits: Dict[str, int] = {}

    def set_limit(self, key: str, limit: int) -> None:
        self._custom_limits[key] = limit

    def get_limit(self, key: str) -> int:
        return self._custom_limits.get(key, self.default_limit)

    def check_and_record(
        self,
        key: str,
        now: float = None
    ) -> Tuple[bool, int, float]:
        """
        Checks whether the key is within rate limits.
        Returns:
            allowed: True if request permitted, False if throttled
            remaining: number of remaining requests in the current window
            retry_after_seconds: time to wait before next window slot opens
        """
        current_time = now if now is not None else time.time()
        cutoff = current_time - self.window_seconds

        timestamps = self._history.setdefault(key, [])
        # Prune older entries
        while timestamps and timestamps[0] < cutoff:
            timestamps.pop(0)

        limit = self.get_limit(key)
        if len(timestamps) >= limit:
            oldest = timestamps[0]
            retry_after = max(0.001, round((oldest + self.window_seconds) - current_time, 2))
            return False, 0, retry_after

        # Record current request
        timestamps.append(current_time)
        remaining = max(0, limit - len(timestamps))
        return True, remaining, 0.0

    def reset(self, key: Optional[str] = None) -> None:
        if key:
            self._history.pop(key, None)
        else:
            self._history.clear()


default_rate_limiter = SlidingWindowRateLimiter()
