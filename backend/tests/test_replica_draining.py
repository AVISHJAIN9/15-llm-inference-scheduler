import pytest
from scheduler.models import InferenceRequest
from routing.router import RequestRouter, WorkerReplica, ReplicaStatus

def test_SCH_083_replica_draining():
    router = RequestRouter()

    # Replicas A and B both host gpt-2
    rep_a = WorkerReplica(worker_id="rep-a", endpoint_url="http://rep-a:8000", loaded_models={"gpt-2"}, active_requests=2)
    rep_b = WorkerReplica(worker_id="rep-b", endpoint_url="http://rep-b:8000", loaded_models={"gpt-2"}, active_requests=10)

    router.register_replica(rep_a)
    router.register_replica(rep_b)

    # Initiate draining on rep-a
    ok = router.drain_replica("rep-a")
    assert ok is True
    assert rep_a.status == ReplicaStatus.DRAINING

    # New request arrives: even though rep-a has only 2 requests vs rep-b's 10,
    # the router MUST NOT route to rep-a because it is DRAINING!
    req = InferenceRequest(request_id="r-drain", model_name="gpt-2", prompt="hi", max_tokens=10)
    target = router.route_request(req)
    assert target is not None
    assert target.worker_id == "rep-b"  # Exclusively routed to healthy replica

    # As in-flight requests finish on rep-a:
    router.update_load("rep-a", delta_requests=-2)
    # Once active_requests reaches 0, rep-a automatically transitions to DRAINED!
    assert rep_a.active_requests == 0
    assert rep_a.status == ReplicaStatus.DRAINED
