import pytest
from scheduler.models import InferenceRequest
from routing.router import RequestRouter, WorkerReplica, ReplicaStatus

def test_SCH_072_gpu_aware_routing():
    """
    SCH-072: GPU-aware routing (BE, P0).
    Routes requests based on real-time GPU metrics (memory headroom, accelerator utilization,
    thermal safety), avoiding saturated or overheated GPU nodes.
    """
    router = RequestRouter()

    # Worker 1: GPU utilization 85%, free memory 8 GB, temp 60C
    w1 = WorkerReplica(
        worker_id="w1",
        endpoint_url="http://worker-1:8000",
        loaded_models={"llama-3-8b"},
        gpu_utilization_pct=85.0,
        gpu_free_memory_bytes=8 * 1024 * 1024 * 1024,
        gpu_temperature_c=60.0
    )
    # Worker 2: GPU utilization 25%, free memory 24 GB, temp 52C (optimal!)
    w2 = WorkerReplica(
        worker_id="w2",
        endpoint_url="http://worker-2:8000",
        loaded_models={"llama-3-8b"},
        gpu_utilization_pct=25.0,
        gpu_free_memory_bytes=24 * 1024 * 1024 * 1024,
        gpu_temperature_c=52.0
    )
    # Worker 3: GPU overheated (90C >= 85C safety limit)
    w3 = WorkerReplica(
        worker_id="w3",
        endpoint_url="http://worker-3:8000",
        loaded_models={"llama-3-8b"},
        gpu_utilization_pct=10.0,
        gpu_free_memory_bytes=40 * 1024 * 1024 * 1024,
        gpu_temperature_c=90.0
    )

    router.register_replica(w1)
    router.register_replica(w2)
    router.register_replica(w3)

    req = InferenceRequest(request_id="req-1", model_name="llama-3-8b", prompt="hello")

    # 1. Routing should pick w2 (lowest utilization 25% vs 85%, overheated w3 excluded)
    best = router.route_gpu_aware(req, min_free_memory_bytes=4 * 1024 * 1024 * 1024)
    assert best is not None
    assert best.worker_id == "w2"

    # 2. Memory threshold: if workload requires 16 GB free memory, w1 (8 GB) is disqualified,
    # w2 (24 GB) is chosen
    heavy_best = router.route_gpu_aware(req, min_free_memory_bytes=16 * 1024 * 1024 * 1024)
    assert heavy_best is not None
    assert heavy_best.worker_id == "w2"

    # 3. Workload requires 32 GB: w1 and w2 disqualified, w3 is overheated -> returns None
    impossible_best = router.route_gpu_aware(req, min_free_memory_bytes=32 * 1024 * 1024 * 1024)
    assert impossible_best is None
