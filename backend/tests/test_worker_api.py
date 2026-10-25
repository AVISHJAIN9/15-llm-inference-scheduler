import pytest
from fastapi.testclient import TestClient
from api.app import app


def test_SCH_105_worker_api():
    """
    SCH-105: Worker API (BE, P0).
    Provides cluster worker lifecycle endpoints:
    - POST /api/v1/workers/register (registers node with GPU info & models)
    - POST /api/v1/workers/{worker_id}/heartbeat (records periodic metrics)
    - GET /api/v1/workers (lists registered worker nodes and load/health status)
    - POST /api/v1/workers/{worker_id}/drain (graceful worker decommissioning)
    """
    client = TestClient(app)

    # 1. Register a new GPU worker
    reg_payload = {
        "worker_id": "worker-gpu-node-1",
        "endpoint_url": "http://10.0.0.1:8000",
        "supported_models": ["llama-3", "gpt-2"],
        "gpu_ids": ["gpu-0", "gpu-1"],
        "max_concurrent_requests": 32
    }
    reg_resp = client.post("/api/v1/workers/register", json=reg_payload)
    assert reg_resp.status_code == 200
    assert reg_resp.json()["status"] == "REGISTERED"
    assert reg_resp.json()["worker_id"] == "worker-gpu-node-1"

    # 2. Heartbeat update with GPU metrics
    hb_payload = {
        "gpu_utilization_pct": 45.5,
        "gpu_free_memory_bytes": 16 * 1024 * 1024 * 1024,
        "gpu_temperature_c": 55.0,
        "active_requests": 4
    }
    hb_resp = client.post("/api/v1/workers/worker-gpu-node-1/heartbeat", json=hb_payload)
    assert hb_resp.status_code == 200
    assert hb_resp.json()["status"] == "OK"

    # 3. GET /api/v1/workers
    list_resp = client.get("/api/v1/workers")
    assert list_resp.status_code == 200
    data = list_resp.json()
    assert data["total_workers"] >= 1
    w_ids = [w["worker_id"] for w in data["workers"]]
    assert "worker-gpu-node-1" in w_ids
    w_info = next(w for w in data["workers"] if w["worker_id"] == "worker-gpu-node-1")
    assert w_info["is_alive"] is True
    assert w_info["status"] == "HEALTHY"
    assert w_info["active_requests"] == 4
    assert w_info["gpu_utilization_pct"] == 45.5

    # 4. Drain worker
    drain_resp = client.post("/api/v1/workers/worker-gpu-node-1/drain")
    assert drain_resp.status_code == 200
    # Has active_requests=4 -> DRAINING
    assert drain_resp.json()["status"] == "DRAINING"

    # 5. Negative test: heartbeat for unknown worker -> 404
    bad_hb = client.post("/api/v1/workers/unknown-worker-99/heartbeat", json={})
    assert bad_hb.status_code == 404
    assert bad_hb.json()["error"]["code"] == "WORKER_NOT_FOUND"
