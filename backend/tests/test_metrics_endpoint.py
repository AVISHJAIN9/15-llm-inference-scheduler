import pytest
from fastapi.testclient import TestClient
from api.app import app

def test_SCH_109_metrics_endpoint():
    """
    SCH-109: Metrics endpoint (BE, P0).
    Prometheus scraping endpoint at /metrics and /api/v1/metrics returning standard text exposition.
    """
    client = TestClient(app)

    # 1. GET /metrics
    resp = client.get("/metrics")
    assert resp.status_code == 200
    assert "text/plain" in resp.headers["content-type"]
    text = resp.text

    assert "llm_scheduler_queue_depth" in text
    assert "llm_scheduler_active_batch_size" in text
    assert "llm_scheduler_kv_blocks_used" in text
    assert "llm_scheduler_kv_blocks_free" in text

    # 2. GET /api/v1/metrics (API v1 path)
    resp_v1 = client.get("/api/v1/metrics")
    assert resp_v1.status_code == 200
    assert "llm_scheduler_queue_depth" in resp_v1.text
