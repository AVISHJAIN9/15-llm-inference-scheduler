import pytest
from fastapi.testclient import TestClient
from api.app import app


def test_SCH_102_scheduler_api():
    """
    SCH-102: Scheduler API (BE, P0).
    Provides scheduler control plane endpoints:
    - GET /api/v1/scheduler/status (active state, policy, batch/queue parameters)
    - POST /api/v1/scheduler/config (dynamic reconfiguration with validation & error envelope)
    """
    client = TestClient(app)

    # 1. Query scheduler status
    resp = client.get("/api/v1/scheduler/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ACTIVE"
    assert "policy" in data
    assert "max_batch_size" in data
    assert "current_queue_depth" in data

    # 2. Update scheduler config dynamically
    update_payload = {
        "policy": "PRIORITY",
        "max_batch_size": 16,
        "max_queue_depth": 2000
    }
    cfg_resp = client.post("/api/v1/scheduler/config", json=update_payload)
    assert cfg_resp.status_code == 200
    cfg_data = cfg_resp.json()
    assert cfg_data["status"] == "UPDATED"
    assert cfg_data["config"]["policy"] == "PRIORITY"
    assert cfg_data["config"]["max_batch_size"] == 16
    assert cfg_data["config"]["max_queue_depth"] == 2000

    # Verify updated status reflects new config
    status_resp = client.get("/api/v1/scheduler/status")
    assert status_resp.status_code == 200
    assert status_resp.json()["policy"] == "PRIORITY"
    assert status_resp.json()["max_batch_size"] == 16
    assert status_resp.json()["max_queue_depth"] == 2000

    # 3. Negative validation test: invalid max_batch_size (must be > 0)
    invalid_resp = client.post("/api/v1/scheduler/config", json={"max_batch_size": 0})
    assert invalid_resp.status_code == 400
    err = invalid_resp.json()["error"]
    assert err["code"] == "INVALID_CONFIG"
    assert "request_id" in err
