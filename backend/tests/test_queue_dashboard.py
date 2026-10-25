import pytest
from fastapi.testclient import TestClient
from api.app import app, queue
from scheduler.models import InferenceRequest

def test_SCH_139_queue_dashboard():
    client = TestClient(app)

    # Enqueue a request directly
    req = InferenceRequest(
        request_id="queue-dash-req-1",
        model_name="gpt-2",
        prompt="Inspect queue test",
        max_tokens=32,
        priority=3
    )
    queue.enqueue(req)

    # Query queue dashboard endpoint
    resp = client.get("/api/v1/dashboard/queue")
    assert resp.status_code == 200
    data = resp.json()

    assert "queue_depth" in data
    assert "max_capacity" in data
    assert "queued_items" in data
    assert data["queue_depth"] >= 1

    # Verify item contents match
    item = next(it for it in data["queued_items"] if it["request_id"] == "queue-dash-req-1")
    assert item["model_name"] == "gpt-2"
    assert item["priority"] == 3
    assert item["max_tokens"] == 32
    assert item["status"] == "QUEUED"

    # Cleanup queue
    queue.remove("queue-dash-req-1")
