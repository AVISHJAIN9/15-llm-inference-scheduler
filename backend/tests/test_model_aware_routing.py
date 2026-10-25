import pytest
from scheduler.models import InferenceRequest
from routing.router import RequestRouter, WorkerReplica, ReplicaStatus

def test_SCH_071_model_aware_routing():
    router = RequestRouter()

    # Worker 1 hosts gpt-2 only
    w1 = WorkerReplica(worker_id="w1", endpoint_url="http://worker-1:8000", loaded_models={"gpt-2"})
    # Worker 2 hosts llama-3 only
    w2 = WorkerReplica(worker_id="w2", endpoint_url="http://worker-2:8000", loaded_models={"llama-3"})
    # Worker 3 hosts both gpt-2 and llama-3
    w3 = WorkerReplica(worker_id="w3", endpoint_url="http://worker-3:8000", loaded_models={"gpt-2", "llama-3"})

    router.register_replica(w1)
    router.register_replica(w2)
    router.register_replica(w3)

    # Request for llama-3 must ONLY route to w2 or w3, never to w1!
    req_llama = InferenceRequest(request_id="r-l", model_name="llama-3", prompt="hi", max_tokens=10)
    target = router.route_request(req_llama)
    assert target is not None
    assert target.worker_id in {"w2", "w3"}
    assert "llama-3" in target.loaded_models

    # Request for an unknown/unhosted model returns None safely
    req_unknown = InferenceRequest(request_id="r-u", model_name="claude-4", prompt="hi", max_tokens=10)
    assert router.route_request(req_unknown) is None
