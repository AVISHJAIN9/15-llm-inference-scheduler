import pytest
from routing.router import RequestRouter, WorkerReplica, ReplicaStatus
from scheduler.models import InferenceRequest

def test_SCH_084_replica_failover():
    """
    SCH-084: Replica failover (BE, P0).
    Automatic failover when replica becomes unhealthy or offline during in-flight execution,
    rerouting active requests to next available healthy replica without duplicate processing.
    """
    router = RequestRouter()
    w1 = WorkerReplica(
        worker_id="w1",
        endpoint_url="http://worker-1:8000",
        loaded_models={"llama-3-8b"},
        active_requests=1,
        status=ReplicaStatus.HEALTHY
    )
    w2 = WorkerReplica(
        worker_id="w2",
        endpoint_url="http://worker-2:8000",
        loaded_models={"llama-3-8b"},
        active_requests=0,
        status=ReplicaStatus.HEALTHY
    )
    router.register_replica(w1)
    router.register_replica(w2)

    req = InferenceRequest(request_id="req-failover-1", model_name="llama-3-8b", prompt="failover test")

    # 1. w1 fails while executing req. Router fails over to w2
    new_worker = router.failover_request(req, failed_worker_id="w1", reason="timeout")
    assert new_worker is not None
    assert new_worker.worker_id == "w2"

    # w1 active_requests decremented and status marked UNHEALTHY
    assert w1.active_requests == 0
    assert w1.status == ReplicaStatus.UNHEALTHY

    # w2 active_requests incremented
    assert w2.active_requests == 1

    # Request has failover history recorded and assigned_worker_id updated
    assert req.assigned_worker_id == "w2"
    assert "failover_history" in req.metadata
    history = req.metadata["failover_history"]
    assert len(history) == 1
    assert history[0]["from_worker"] == "w1"
    assert history[0]["to_worker"] == "w2"
    assert history[0]["reason"] == "timeout"


    # 2. If w2 now fails and no other healthy replicas have llama-3-8b, returns None
    no_worker = router.failover_request(req, failed_worker_id="w2", reason="crash")
    assert no_worker is None
    assert w2.active_requests == 0
    assert w2.status == ReplicaStatus.UNHEALTHY
