import pytest
from clock import Clock
from scheduler.models import InferenceRequest, RequestStatus
from scheduler.queue import FIFOQueue
from coordination.dispatch import DispatchCoordinator
from coordination.workers import WorkerRegistry
from coordination.recovery import FailureRecoveryManager

def test_SCH_097_at_least_once_recovery():
    clk = Clock(initial_time=100.0)
    registry = WorkerRegistry(clock=clk, heartbeat_timeout=10.0)
    dispatch_coord = DispatchCoordinator(clock=clk)
    queue = FIFOQueue(max_capacity=100)

    recovery = FailureRecoveryManager(registry, dispatch_coord, queue)

    # Register worker-fail
    registry.register_worker("worker-fail", "http://fail:8000", {"gpt-2"})

    # Dispatch request to worker-fail
    req = InferenceRequest(request_id="req-recovered-1", model_name="gpt-2", prompt="important task", max_tokens=10)
    ok_disp, _ = dispatch_coord.dispatch("req-recovered-1", "worker-fail", fencing_token=1)
    assert ok_disp is True
    recovery.track_request("worker-fail", req)

    # Advance clock past heartbeat timeout (10s -> advance 15s to 115.0)
    clk.advance(15.0)
    dead = registry.check_dead_workers()
    assert dead == ["worker-fail"]

    # Trigger recovery
    requeued = recovery.recover_dead_workers()
    assert len(requeued) == 1
    assert requeued[0].request_id == "req-recovered-1"
    assert requeued[0].status == RequestStatus.QUEUED

    # Verify request is now in queue and dispatch lock was cleared
    assert queue.size() == 1
    next_req = queue.dequeue()
    assert next_req.request_id == "req-recovered-1"

    # Re-dispatch to new healthy worker succeeds (zero lost requests!)
    ok_redisp, _ = dispatch_coord.dispatch("req-recovered-1", "worker-healthy", fencing_token=2)
    assert ok_redisp is True
