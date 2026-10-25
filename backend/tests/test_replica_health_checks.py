import pytest
from routing.router import RequestRouter, WorkerReplica, ReplicaStatus
from scheduler.models import InferenceRequest

def test_SCH_082_replica_health_checks():
    """
    SCH-082: Replica health checks (BE, P0).
    Active health probe tracking, failure/success threshold state transitions,
    and automatic recovery.
    """
    router = RequestRouter()
    w1 = WorkerReplica(
        worker_id="w1",
        endpoint_url="http://worker-1:8000",
        loaded_models={"llama-3-8b"},
        status=ReplicaStatus.HEALTHY
    )
    router.register_replica(w1)

    # 1. Successful health probes keep it HEALTHY and record latency
    st = router.record_health_probe("w1", success=True, latency_ms=15.0)
    assert st == ReplicaStatus.HEALTHY
    assert w1.status == ReplicaStatus.HEALTHY
    assert w1.avg_latency_ms > 0.0

    # 2. First failure -> transitions to UNHEALTHY (not yet OFFLINE since failure_threshold=3)
    st = router.record_health_probe("w1", success=False, failure_threshold=3)
    assert st == ReplicaStatus.UNHEALTHY
    assert w1.status == ReplicaStatus.UNHEALTHY

    # Routing should not route to UNHEALTHY replica
    req = InferenceRequest(request_id="req-1", model_name="llama-3-8b", prompt="hi")
    assert router.route_request(req) is None

    # 3. Consecutive failures reach threshold (3 total failures) -> transitions to OFFLINE
    router.record_health_probe("w1", success=False, failure_threshold=3)
    st3 = router.record_health_probe("w1", success=False, failure_threshold=3)
    assert st3 == ReplicaStatus.OFFLINE
    assert w1.status == ReplicaStatus.OFFLINE

    # 4. Recovery: single success is not enough (success_threshold=2)
    st4 = router.record_health_probe("w1", success=True, success_threshold=2)
    assert st4 == ReplicaStatus.OFFLINE  # Still offline until 2 consecutive successes

    # Second consecutive success -> recovers to HEALTHY
    st5 = router.record_health_probe("w1", success=True, success_threshold=2)
    assert st5 == ReplicaStatus.HEALTHY
    assert w1.status == ReplicaStatus.HEALTHY

    # Now routing works again
    assigned = router.route_request(req)
    assert assigned is not None
    assert assigned.worker_id == "w1"
