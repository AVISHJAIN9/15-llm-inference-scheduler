import pytest
from scheduler.models import InferenceRequest
from routing.router import RequestRouter, WorkerReplica, ReplicaStatus

def test_SCH_074_queue_length_routing():
    """
    SCH-074: Queue-length routing (BE, P0).
    Route based on worker queue depth (pending requests/tokens).
    Route to least queued worker, support max queue threshold before shedding.
    """
    router = RequestRouter()

    # Worker 1: queue_length = 15
    w1 = WorkerReplica(
        worker_id="w1",
        endpoint_url="http://worker-1:8000",
        loaded_models={"llama-3-8b"},
        queue_length=15,
        active_requests=4
    )
    # Worker 2: queue_length = 3 (least queued!)
    w2 = WorkerReplica(
        worker_id="w2",
        endpoint_url="http://worker-2:8000",
        loaded_models={"llama-3-8b"},
        queue_length=3,
        active_requests=2
    )
    # Worker 3: queue_length = 50 (at or above threshold 50)
    w3 = WorkerReplica(
        worker_id="w3",
        endpoint_url="http://worker-3:8000",
        loaded_models={"llama-3-8b"},
        queue_length=50,
        active_requests=10
    )

    router.register_replica(w1)
    router.register_replica(w2)
    router.register_replica(w3)

    req = InferenceRequest(request_id="req-1", model_name="llama-3-8b", prompt="hello")

    # 1. Routing should pick w2 (queue_length 3 vs 15)
    best = router.route_queue_length(req, max_queue_depth=40)
    assert best is not None
    assert best.worker_id == "w2"

    # 2. If w2 queue jumps to 20, router should pick w1 (15 vs 20)
    w2.queue_length = 20
    best2 = router.route_queue_length(req, max_queue_depth=40)
    assert best2 is not None
    assert best2.worker_id == "w1"

    # 3. Shedding: if max_queue_depth=10, all workers (15, 20, 50) exceed max depth -> returns None
    shed = router.route_queue_length(req, max_queue_depth=10)
    assert shed is None
