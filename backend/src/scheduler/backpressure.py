"""
Backpressure controller for LLM inference scheduling (SCH-012).
Implements watermark hysteresis, retry-after guidance, and explicit rejection under load.
"""

from typing import Dict, Any, Optional

class BackpressureController:
    def __init__(self, high_watermark: int = 100, low_watermark: int = 70, base_retry_after_ms: int = 500):
        if low_watermark >= high_watermark:
            raise ValueError("low_watermark must be strictly less than high_watermark")
        self.high_watermark = high_watermark
        self.low_watermark = low_watermark
        self.base_retry_after_ms = base_retry_after_ms
        self._backpressured: bool = False
        self._total_rejections: int = 0

    def update_depth(self, current_depth: int) -> bool:
        """
        Updates queue depth and returns whether backpressure is active.
        Uses hysteresis: trips at high_watermark, recovers only below low_watermark.
        """
        if not self._backpressured and current_depth >= self.high_watermark:
            self._backpressured = True
        elif self._backpressured and current_depth <= self.low_watermark:
            self._backpressured = False
        return self._backpressured

    def is_backpressured(self) -> bool:
        return self._backpressured

    def check_admission(self, current_depth: int) -> Dict[str, Any]:
        """
        Checks if a new request can be admitted or if backpressure rejects it.
        """
        is_bp = self.update_depth(current_depth)
        if is_bp:
            self._total_rejections += 1
            # Calculate dynamic retry-after based on excess depth
            excess = max(1, current_depth - self.low_watermark)
            retry_after_ms = self.base_retry_after_ms + (excess * 50)
            return {
                "admitted": False,
                "status_code": 429,
                "reason": "Queue backpressure active: server saturated",
                "retry_after_seconds": round(retry_after_ms / 1000.0, 2),
                "current_depth": current_depth,
                "high_watermark": self.high_watermark
            }
        return {
            "admitted": True,
            "status_code": 200,
            "reason": "Admitted",
            "current_depth": current_depth
        }

    @property
    def total_rejections(self) -> int:
        return self._total_rejections
