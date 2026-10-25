import pytest
from clock import Clock
from coordination.workers import WorkerRegistry

def test_SCH_090_worker_registration():
    clk = Clock(initial_time=50.0)
    registry = WorkerRegistry(clock=clk)

    # Register worker
    meta = registry.register_worker(
        worker_id="worker-gpu-1",
        endpoint_url="http://10.0.0.1:8000",
        supported_models={"gpt-2", "qwen2.5-0.5b"},
        gpu_ids=["gpu-0", "gpu-1"],
        max_concurrent_requests=8
    )

    assert meta.worker_id == "worker-gpu-1"
    assert meta.endpoint_url == "http://10.0.0.1:8000"
    assert "gpt-2" in meta.supported_models
    assert len(meta.gpu_ids) == 2
    assert meta.registered_at == 50.0
    assert meta.last_heartbeat == 50.0
    assert meta.is_alive is True

    # Lookup
    fetched = registry.get_worker("worker-gpu-1")
    assert fetched is not None
    assert fetched.max_concurrent_requests == 8

    # Re-registration idempotently updates properties
    meta_updated = registry.register_worker(
        worker_id="worker-gpu-1",
        endpoint_url="http://10.0.0.1:8001",
        supported_models={"gpt-2", "qwen2.5-0.5b", "llama-3"},
        gpu_ids=["gpu-0", "gpu-1", "gpu-2"],
        max_concurrent_requests=16
    )
    assert meta_updated.endpoint_url == "http://10.0.0.1:8001"
    assert len(meta_updated.supported_models) == 3
    assert meta_updated.max_concurrent_requests == 16
