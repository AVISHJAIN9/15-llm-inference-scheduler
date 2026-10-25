import pytest
from scheduler.models import InferenceRequest
from routing.router import RequestRouter, WorkerReplica, ReplicaStatus

def test_SCH_075_latency_aware_routing():
    """
    SCH-075: Latency-aware routing (BE, P0).
    EWMA latency tracking per replica (TTFT, ITL).
    Route to replica with lowest EWMA latency, decay old samples.
    """
    router = RequestRouter()

    w1 = WorkerReplica(
        worker_id="w1",
        endpoint_url="http://worker-1:8000",
        loaded_models={"llama-3-8b"}
    )
    w2 = WorkerReplica(
        worker_id="w2",
        endpoint_url="http://worker-2:8000",
        loaded_models={"llama-3-8b"}
    )
    w3 = WorkerReplica(
        worker_id="w3",
        endpoint_url="http://worker-3:8000",
        loaded_models={"llama-3-8b"}
    )

    # w1 records higher latencies (TTFT=120ms, ITL=30ms -> 150ms)
    w1.record_latency(ttft_ms=120.0, itl_ms=30.0)
    w1.record_latency(ttft_ms=130.0, itl_ms=30.0)

    # w2 records lower latencies (TTFT=30ms, ITL=10ms -> 40ms)
    w2.record_latency(ttft_ms=30.0, itl_ms=10.0)
    w2.record_latency(ttft_ms=35.0, itl_ms=10.0)

    # w3 records very high latencies (TTFT=800ms, ITL=300ms -> 1100ms)
    w3.record_latency(ttft_ms=800.0, itl_ms=300.0)

    router.register_replica(w1)
    router.register_replica(w2)
    router.register_replica(w3)

    req = InferenceRequest(request_id="req-1", model_name="llama-3-8b", prompt="hello")

    # 1. Route picks w2 with lowest EWMA latency (~41ms vs ~152ms)
    best = router.route_latency_aware(req)
    assert best is not None
    assert best.worker_id == "w2"
    assert best.ewma_ttft_ms < 50.0

    # 2. EWMA decay check: w2 suffers sudden degradation (TTFT=500ms, ITL=200ms)
    for _ in range(10):
        w2.record_latency(ttft_ms=500.0, itl_ms=200.0)
    
    # Now w1 (~152ms) is faster than w2 (~600ms+)
    best2 = router.route_latency_aware(req)
    assert best2 is not None
    assert best2.worker_id == "w1"

    # 3. Maximum acceptable latency threshold (e.g. 100ms) -> both w1 (150ms) and w2 (600ms) and w3 (1100ms) exceed
    strict = router.route_latency_aware(req, max_acceptable_latency_ms=100.0)
    assert strict is None
