import pytest
from scheduler.models import InferenceRequest
from routing.router import RequestRouter, WorkerReplica

def test_SCH_073_least_loaded_routing():
    router = RequestRouter()

    # Three replicas all hosting gpt-2, with different loads
    w1 = WorkerReplica(worker_id="w1", endpoint_url="http://w1:8000", loaded_models={"gpt-2"}, active_requests=5, active_tokens=500)
    w2 = WorkerReplica(worker_id="w2", endpoint_url="http://w2:8000", loaded_models={"gpt-2"}, active_requests=1, active_tokens=100)
    w3 = WorkerReplica(worker_id="w3", endpoint_url="http://w3:8000", loaded_models={"gpt-2"}, active_requests=3, active_tokens=300)

    router.register_replica(w1)
    router.register_replica(w2)
    router.register_replica(w3)

    req = InferenceRequest(request_id="r1", model_name="gpt-2", prompt="hi", max_tokens=10)

    # w2 has the lowest load (1 active request vs 3 and 5) -> must be chosen
    target = router.route_request(req)
    assert target is not None
    assert target.worker_id == "w2"

    # Simulate load increase on w2
    router.update_load("w2", delta_requests=3, delta_tokens=300)  # w2 now has 4 active requests
    # Now w3 has lowest load (3 active requests) -> must be chosen
    target2 = router.route_request(req)
    assert target2 is not None
    assert target2.worker_id == "w3"
