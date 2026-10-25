import pytest
from fastapi.testclient import TestClient
from api.app import app

def test_SCH_112_prometheus_metrics_endpoint():
    client = TestClient(app)

    # 1. Fetch /metrics endpoint
    resp = client.get("/metrics")
    assert resp.status_code == 200
    assert "text/plain" in resp.headers["content-type"]
    text = resp.text

    # 2. Verify metric definitions exist
    assert "llm_scheduler_requests_total" in text
    assert "llm_scheduler_queue_depth" in text
    assert "llm_scheduler_active_batch_size" in text
    assert "llm_scheduler_kv_blocks_used" in text
    assert "llm_scheduler_kv_blocks_free" in text

    # 3. Perform an inference request and verify counters increment
    client.post("/api/v1/inference", json={
        "model_name": "gpt-2",
        "prompt": "test prompt",
        "max_tokens": 2
    })

    resp2 = client.get("/metrics")
    assert 'llm_scheduler_requests_total{model="gpt-2",status="completed"}' in resp2.text
