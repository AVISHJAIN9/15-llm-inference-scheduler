import pytest
from fastapi.testclient import TestClient
from api.app import app, system_health_status

def test_SCH_107_health_endpoint():
    """
    SCH-107: Health endpoint (BE, P0).
    Liveness and operational health probes at /healthz and /api/v1/healthz.
    Returns 200 with component statuses when healthy, and 503 when degraded.
    """
    client = TestClient(app)

    # 1. Healthy state
    system_health_status["healthy"] = True
    system_health_status["reason"] = "Operating normally"

    resp = client.get("/healthz")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "HEALTHY"
    assert "uptime_seconds" in data
    assert data["components"]["scheduler"] == "UP"
    assert data["components"]["kv_cache"] == "UP"
    assert data["components"]["queue"] == "UP"

    # API v1 alias
    resp_v1 = client.get("/api/v1/healthz")
    assert resp_v1.status_code == 200
    assert resp_v1.json()["status"] == "HEALTHY"

    # 2. Degraded state -> returns 503 SERVICE_UNAVAILABLE
    system_health_status["healthy"] = False
    system_health_status["reason"] = "Storage volume offline"

    unhealthy_resp = client.get("/healthz")
    assert unhealthy_resp.status_code == 503
    err_data = unhealthy_resp.json()
    assert err_data["error"]["code"] == "SERVICE_UNHEALTHY"
    assert "Storage volume offline" in err_data["error"]["message"]

    # Restore healthy state for clean teardown
    system_health_status["healthy"] = True
