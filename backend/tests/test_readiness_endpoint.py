import pytest
from fastapi.testclient import TestClient
from api.app import app, queue, system_readiness_status
from scheduler.models import InferenceRequest

def test_SCH_108_readiness_endpoint():
    """
    SCH-108: Readiness endpoint (BE, P0).
    Probes system capacity to accept new inference traffic at /readyz and /api/v1/readyz.
    Returns 200 READY when capacity is available; returns 503 NOT_READY when queue is full.
    """
    client = TestClient(app)

    # 1. System is ready
    system_readiness_status["ready"] = True
    system_readiness_status["reason"] = "Ready to accept traffic"

    resp = client.get("/readyz")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "READY"
    assert "queue_depth" in data
    assert "active_batch" in data
    assert "kv_free_blocks" in data

    # API v1 alias
    resp_v1 = client.get("/api/v1/readyz")
    assert resp_v1.status_code == 200
    assert resp_v1.json()["status"] == "READY"

    # 2. Simulate queue saturation (queue_depth >= max_capacity) -> returns 503 NOT_READY
    orig_capacity = queue.max_capacity
    queue.max_capacity = 2
    req1 = InferenceRequest(request_id="r-ready-1", model_name="gpt-2", prompt="hi")
    req2 = InferenceRequest(request_id="r-ready-2", model_name="gpt-2", prompt="hi")
    queue.enqueue(req1)
    queue.enqueue(req2)

    saturated_resp = client.get("/readyz")
    assert saturated_resp.status_code == 503
    err_data = saturated_resp.json()
    assert err_data["error"]["code"] == "NOT_READY"
    assert "capacity" in err_data["error"]["message"].lower()

    # Cleanup queue and restore capacity
    queue.dequeue()
    queue.dequeue()
    queue.max_capacity = orig_capacity

    # Verify back to READY
    restored = client.get("/readyz")
    assert restored.status_code == 200
    assert restored.json()["status"] == "READY"
