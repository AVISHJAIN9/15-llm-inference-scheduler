import pytest
from scheduler.backpressure import BackpressureController

def test_SCH_012_backpressure_hysteresis_and_rejection():
    # High watermark = 10, Low watermark = 5
    bp = BackpressureController(high_watermark=10, low_watermark=5, base_retry_after_ms=400)
    assert not bp.is_backpressured()

    # Depth below high watermark (e.g. 8) -> admitted
    res = bp.check_admission(current_depth=8)
    assert res["admitted"] is True
    assert res["status_code"] == 200
    assert not bp.is_backpressured()

    # Depth hits 10 -> backpressure trips, 429 returned
    res = bp.check_admission(current_depth=10)
    assert res["admitted"] is False
    assert res["status_code"] == 429
    assert res["retry_after_seconds"] > 0
    assert bp.is_backpressured()
    assert bp.total_rejections == 1

    # Depth drops to 8 -> STILL backpressured due to hysteresis!
    res = bp.check_admission(current_depth=8)
    assert res["admitted"] is False
    assert res["status_code"] == 429
    assert bp.is_backpressured()

    # Depth drops to 5 -> recovers, backpressure clears
    res = bp.check_admission(current_depth=5)
    assert res["admitted"] is True
    assert res["status_code"] == 200
    assert not bp.is_backpressured()
