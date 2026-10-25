import pytest
from fastapi.testclient import TestClient
from api.app import app, queue
from scheduler.models import InferenceRequest


def test_SCH_103_queue_api():
    """
    SCH-103: Queue API (BE, P0).
    Provides queue control endpoints:
    - GET /api/v1/queues (total depth and per-model queue statistics)
    - GET /api/v1/queues/{model_name} (filtered inspection of queued requests)
    - DELETE /api/v1/queues/{request_id} (cancellation/purge from queue)
    """
    client = TestClient(app)

    # 1. Enqueue requests directly to queue for inspection
    req1 = InferenceRequest(request_id="q-req-1", model_name="llama-3", prompt="p1", priority=5)
    req2 = InferenceRequest(request_id="q-req-2", model_name="llama-3", prompt="p2", priority=1)
    req3 = InferenceRequest(request_id="q-req-3", model_name="gpt-2", prompt="p3", priority=2)
    queue.enqueue(req1)
    queue.enqueue(req2)
    queue.enqueue(req3)

    # 2. GET /api/v1/queues
    q_resp = client.get("/api/v1/queues")
    assert q_resp.status_code == 200
    q_data = q_resp.json()
    assert q_data["total_queued"] >= 3
    assert q_data["queues_by_model"]["llama-3"] >= 2
    assert q_data["queues_by_model"]["gpt-2"] >= 1

    # 3. GET /api/v1/queues/{model_name}
    model_resp = client.get("/api/v1/queues/llama-3")
    assert model_resp.status_code == 200
    m_data = model_resp.json()
    assert m_data["model_name"] == "llama-3"
    assert m_data["count"] >= 2
    req_ids = [r["request_id"] for r in m_data["requests"]]
    assert "q-req-1" in req_ids
    assert "q-req-2" in req_ids

    # 4. DELETE /api/v1/queues/{request_id} (Cancel/Purge)
    del_resp = client.delete("/api/v1/queues/q-req-1")
    assert del_resp.status_code == 200
    assert del_resp.json()["status"] == "CANCELLED"
    assert del_resp.json()["request_id"] == "q-req-1"

    # Verify q-req-1 is no longer in queue
    after_del = client.get("/api/v1/queues/llama-3")
    after_ids = [r["request_id"] for r in after_del.json()["requests"]]
    assert "q-req-1" not in after_ids

    # 5. Negative test: deleting non-existent request -> 404 NOT_FOUND
    err_resp = client.delete("/api/v1/queues/nonexistent-999")
    assert err_resp.status_code == 404
    assert err_resp.json()["error"]["code"] == "NOT_FOUND"

    # Cleanup remaining test requests
    client.delete("/api/v1/queues/q-req-2")
    client.delete("/api/v1/queues/q-req-3")
