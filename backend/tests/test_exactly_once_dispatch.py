import pytest
from clock import Clock
from coordination.dispatch import DispatchCoordinator

def test_SCH_096_effectively_once_dispatch_semantics():
    clk = Clock(initial_time=500.0)
    coord = DispatchCoordinator(clock=clk)

    # 1. Leader with fencing token 1 dispatches req-100 to worker-1 -> succeeds
    ok1, reason1 = coord.dispatch(request_id="req-100", worker_id="worker-1", fencing_token=1)
    assert ok1 is True
    assert coord.is_in_flight("req-100") is True

    # 2. Stale deposed leader (fencing token 0) attempts dispatch -> strictly rejected
    ok_stale, reason_stale = coord.dispatch(request_id="req-101", worker_id="worker-2", fencing_token=0)
    assert ok_stale is False
    assert "Stale fencing token" in reason_stale

    # 3. Duplicate dispatch of req-100 to worker-2 is strictly prevented
    ok_dup, reason_dup = coord.dispatch(request_id="req-100", worker_id="worker-2", fencing_token=1)
    assert ok_dup is False
    assert "already in-flight" in reason_dup

    # 4. Worker-1 completes execution
    completed = coord.complete_dispatch("req-100", "worker-1")
    assert completed is True
    assert coord.is_in_flight("req-100") is False

    # 5. Subsequent dispatch attempt of req-100 is rejected as already completed
    ok_after, reason_after = coord.dispatch(request_id="req-100", worker_id="worker-3", fencing_token=1)
    assert ok_after is False
    assert "already been completed" in reason_after
