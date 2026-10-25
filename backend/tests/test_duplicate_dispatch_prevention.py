import pytest
from clock import Clock
from coordination.dispatch import DispatchCoordinator

def test_SCH_098_duplicate_dispatch_prevention():
    coord = DispatchCoordinator()

    # Dispatched once
    ok, _ = coord.dispatch("req-dup-test", "w-alpha", fencing_token=10)
    assert ok is True

    # 5 concurrent / repeated dispatch attempts of the same request_id to different workers
    for target in ["w-beta", "w-gamma", "w-delta", "w-alpha"]:
        ok_dup, msg = coord.dispatch("req-dup-test", target, fencing_token=10)
        assert ok_dup is False
        assert "already in-flight" in msg

    # Verify that w-alpha remains the sole dispatched worker
    rec = coord.get_dispatch("req-dup-test")
    assert rec.worker_id == "w-alpha"
    assert rec.is_completed is False
