import pytest
from coordination.discovery import (
    WorkerDiscoveryService,
    WorkerAnnouncement,
    DiscoveredWorker
)
from clock import Clock

def test_SCH_092_worker_discovery():
    """
    SCH-092: Worker discovery (BE, P0).
    Dynamic worker discovery with automated capability negotiation,
    health probe verification, and resource-based filtering.
    """
    clock = Clock(initial_time=500.0)
    service = WorkerDiscoveryService(clock=clock)

    # 1. Announce worker 1 with A100 GPU and 80GB memory
    a1 = WorkerAnnouncement(
        worker_id="w-gpu-1",
        endpoint_url="http://worker-1.cluster.local:8000",
        supported_models={"llama-3-70b", "llama-3-8b"},
        gpu_type="NVIDIA-A100-SXM4-80GB",
        gpu_memory_bytes=80 * 1024 * 1024 * 1024,
        max_batch_tokens=16384
    )
    # Announce worker 2 with T4 GPU (smaller memory 16GB)
    a2 = WorkerAnnouncement(
        worker_id="w-gpu-2",
        endpoint_url="http://worker-2.cluster.local:8000",
        supported_models={"llama-3-8b"},
        gpu_type="NVIDIA-T4",
        gpu_memory_bytes=16 * 1024 * 1024 * 1024,
        max_batch_tokens=4096
    )

    w1 = service.announce_worker(a1)
    w2 = service.announce_worker(a2)

    assert w1.status == "UNVERIFIED"
    assert w2.status == "UNVERIFIED"

    # 2. Automated capability verification probe
    assert service.verify_worker(worker_id="w-gpu-1", probe_success=True) is True
    assert service.verify_worker(worker_id="w-gpu-2", probe_success=True) is True
    assert w1.status == "VERIFIED"
    assert w2.status == "VERIFIED"

    # 3. Capability negotiation & discovery filtering
    # Search for workers capable of running large model llama-3-70b with >= 64GB GPU memory
    heavy_workers = service.find_workers(
        model_name="llama-3-70b",
        min_gpu_memory_bytes=64 * 1024 * 1024 * 1024
    )
    assert len(heavy_workers) == 1
    assert heavy_workers[0].announcement.worker_id == "w-gpu-1"

    # Search for llama-3-8b with batch size >= 2048 -> both workers qualify
    light_workers = service.find_workers(
        model_name="llama-3-8b",
        min_max_batch_tokens=2048
    )
    assert len(light_workers) == 2

    # 4. Failed health verification removes worker from verified discovery pool
    service.verify_worker(worker_id="w-gpu-2", probe_success=False)
    assert w2.status == "FAILED"

    active_pool = service.find_workers(model_name="llama-3-8b")
    assert len(active_pool) == 1
    assert active_pool[0].announcement.worker_id == "w-gpu-1"
