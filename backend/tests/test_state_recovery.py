import pytest
from clock import Clock
from scheduler.models import InferenceRequest, RequestStatus
from coordination.state_recovery import SchedulerStateRecoveryManager


def test_SCH_095_state_recovery():
    """
    SCH-095: State recovery (BE, P0, rank 2).
    Enforces Invariant P15 §9:
    "scheduler state recovery after crash yields zero lost and zero duplicated requests"
    Recovers pending queue, reconciles in-flight dispatches across crashed and alive workers,
    and proves zero lost and zero duplicated requests.
    """
    clk = Clock(initial_time=500.0)
    recovery_mgr = SchedulerStateRecoveryManager(clock=clk)

    # 1. Submit 10 requests
    for i in range(1, 11):
        req = InferenceRequest(
            request_id=f"req-{i}",
            model_name="llama-3-8b",
            prompt=f"prompt {i}",
            arrival_time=clk.now()
        )
        recovery_mgr.submit_request(req)

    # 2. Dispatch 6 requests across workers:
    # w1 gets req-1, req-2, req-3
    # w2 gets req-4, req-5, req-6
    # pending queue holds req-7, req-8, req-9, req-10 (4 requests)
    for i in range(1, 4):
        recovery_mgr.dispatch_request(f"req-{i}", worker_id="w1")
    for i in range(4, 7):
        recovery_mgr.dispatch_request(f"req-{i}", worker_id="w2")

    # 3. Before crash, w1 successfully finishes and acks req-1 and req-2
    assert recovery_mgr.acknowledge_completion("req-1") is True
    assert recovery_mgr.acknowledge_completion("req-2") is True

    # 4. CRASH EVENT!
    # w1 crashes while req-3 is still in-flight
    # w2 remains alive with req-4, req-5, req-6
    # Scheduler crashes, reboots, and runs state recovery
    active_workers = {"w2"}
    unreachable_workers = {"w1"}

    report = recovery_mgr.recover_after_crash(
        active_worker_ids=active_workers,
        unreachable_worker_ids=unreachable_workers
    )

    # 5. Assert Invariant P15 §9 guarantees:
    # Zero lost requests
    assert report.zero_lost is True
    # Zero duplicated requests
    assert report.zero_duplicated is True

    # Detailed accounting:
    assert report.total_submitted == 10
    assert report.recovered_completed == 2  # req-1, req-2
    assert report.recovered_in_flight == 3   # req-4, req-5, req-6 on healthy w2
    assert report.recovered_queued == 5      # 4 originally queued (7-10) + req-3 recovered from crashed w1!

    # Verify req-3 was re-queued and can be cleanly processed
    queued_ids = [r.request_id for r in recovery_mgr.get_pending_queue()]
    assert "req-3" in queued_ids
    assert queued_ids == ["req-7", "req-8", "req-9", "req-10", "req-3"]
