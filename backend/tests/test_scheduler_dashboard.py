import pytest
from fastapi.testclient import TestClient
from api.app import app, batcher

def test_SCH_138_scheduler_dashboard():
    client = TestClient(app)

    # Query dashboard stats endpoint
    resp = client.get("/api/v1/dashboard/stats")
    assert resp.status_code == 200
    data = resp.json()

    # Verify all essential metrics for SCH-138 dashboard
    assert "active_batch_size" in data
    assert "max_batch_size" in data
    assert "kv_blocks_used" in data
    assert "kv_blocks_free" in data
    assert "kv_blocks_total" in data
    assert "iteration_count" in data
    assert "queue_depth" in data
    assert "uptime_seconds" in data

    assert data["max_batch_size"] == batcher.max_batch_size
    assert data["kv_blocks_total"] == batcher.kv_manager.total_blocks
    assert data["kv_blocks_used"] >= 0
    assert data["kv_blocks_free"] >= 0
