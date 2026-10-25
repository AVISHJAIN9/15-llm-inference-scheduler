import pytest
from coordination.recovery import SchedulerCrashRecoveryEngine, RecoverySummary
from coordination.workers import WorkerRegistry
from coordination.dispatch import DispatchCoordinator
from scheduler.queue import FIFOQueue
from scheduler.models import InferenceRequest, RequestStatus
from clock import Clock

def test_SCH_095_state_recovery():
    """
    SCH-095: State recovery (BE, P0).
    Scheduler state recovery after crash: reconciles durable DB requests,
    worker liveness, and in-flight queue state.
    Guarantees zero lost and zero duplicated requests (Phase 2 invariant & S15-04).
    """
    clock = Clock(initial_time=2000.0)
    worker_registry = WorkerRegistry(clock=clock, heartbeat_timeout=5.0)
    dispatch_coord = DispatchCoordinator(clock=clock)
    queue = FIFOQueue()

    # 1. Register workers: worker-1 is alive; worker-2 is dead (timed out)
    worker_registry.register_worker("worker-1", "http://w1:8000", supported_models={"llama-3-8b"})
    worker_registry.register_worker("worker-2", "http://w2:8000", supported_models={"llama-3-8b"})

    # Advance clock by 10s and only heartbeat worker-1
    clock.advance(10.0)
    worker_registry.record_heartbeat("worker-1")

    # Persisted requests from database prior to scheduler crash:
    # req-1: was IN_FLIGHT on healthy worker-1
    req1 = InferenceRequest(
        request_id="req-1",
        model_name="llama-3-8b",
        prompt="p1",
        status=RequestStatus.IN_FLIGHT,
        assigned_worker_id="worker-1"
    )
    # req-2: was IN_FLIGHT on dead worker-2 -> must be recovered and re-queued
    req2 = InferenceRequest(
        request_id="req-2",
        model_name="llama-3-8b",
        prompt="p2",
        status=RequestStatus.IN_FLIGHT,
        assigned_worker_id="worker-2"
    )
    # req-3: was QUEUED in pending backlog -> must remain in queue
    req3 = InferenceRequest(
        request_id="req-3",
        model_name="llama-3-8b",
        prompt="p3",
        status=RequestStatus.QUEUED
    )
    # req-4: was already COMPLETED -> must be registered in dedupe store to prevent duplicate execution
    req4 = InferenceRequest(
        request_id="req-4",
        model_name="llama-3-8b",
        prompt="p4",
        status=RequestStatus.COMPLETED,
        assigned_worker_id="worker-1"
    )

    persisted_requests = [req1, req2, req3, req4]

    engine = SchedulerCrashRecoveryEngine(
        worker_registry=worker_registry,
        dispatch_coordinator=dispatch_coord,
        queue=queue
    )

    summary: RecoverySummary = engine.recover_from_persistent_store(persisted_requests)

    # 2. Invariant assertions: Zero lost, zero duplicated requests
    assert summary.zero_lost is True
    assert summary.zero_duplicated is True
    assert summary.total_reconciled == 4
    assert summary.requeued_count == 2  # req-2 (from dead worker) + req-3 (pending backlog)
    assert summary.retained_in_flight_count == 1  # req-1 (on healthy worker-1)
    assert summary.completed_deduped_count == 1  # req-4

    # 3. Queue assertions
    assert queue.size() == 2
    queued_ids = [queue.dequeue().request_id for _ in range(2)]
    assert "req-2" in queued_ids
    assert "req-3" in queued_ids

    # 4. Duplicate prevention assertion: Attempting to dispatch already completed req-4 is rejected
    dup_ok, dup_msg = dispatch_coord.dispatch("req-4", "worker-1", fencing_token=1)
    assert dup_ok is False
    assert "already been completed" in dup_msg
