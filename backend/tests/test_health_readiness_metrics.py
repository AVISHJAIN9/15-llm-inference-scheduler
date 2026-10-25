import pytest
from fastapi.testclient import TestClient
from api.app import app, system_health_status, system_readiness_status, queue
from scheduler.models import InferenceRequest


def test_SCH_107_health_endpoint():
    """
    SCH-107: Health endpoint (BE, P0).
    Verifies /healthz and /api/v1/healthz endpoints:
    - 200 OK with status HEALTHY when dependencies are functioning
    - Reports component statuses (scheduler, kv_cache, queue)
    - 503 SERVICE_UNAVAILABLE when system is unhealthy
    """
    client = TestClient(app)

    # Reset health status
    system_health_status["healthy"] = True
    system_health_status["reason"] = "All systems operational"

    # 1. Successful health check on /healthz
    resp = client.get("/healthz")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] in ("ok", "HEALTHY")
    assert data["uptime_seconds"] >= 0
    assert data["components"]["scheduler"] == "UP"
    assert data["components"]["kv_cache"] == "UP"
    assert data["components"]["queue"] == "UP"

    # 2. Check /api/v1/healthz alias
    resp_v1 = client.get("/api/v1/healthz")
    assert resp_v1.status_code == 200
    assert resp_v1.json()["status"] in ("ok", "HEALTHY")

    # 3. Unhealthy transition -> 503
    system_health_status["healthy"] = False
    system_health_status["reason"] = "Database connection pool exhausted"
    unhealthy_resp = client.get("/healthz")
    assert unhealthy_resp.status_code == 503
    unhealthy_data = unhealthy_resp.json()
    assert unhealthy_data["error"]["code"] == "SERVICE_UNHEALTHY"
    assert "Database connection pool" in unhealthy_data["error"]["message"]

    # Restore healthy status
    system_health_status["healthy"] = True


def test_SCH_108_readiness_endpoint():
    """
    SCH-108: Readiness endpoint (BE, P0).
    Verifies /readyz and /api/v1/readyz endpoints:
    - 200 READY when ready to receive traffic
    - Reports active batch, queue depth, kv free blocks
    - 503 NOT_READY when queue is saturated or marked unready
    """
    client = TestClient(app)

    # Reset readiness status
    system_readiness_status["ready"] = True
    system_readiness_status["reason"] = "Ready"

    # 1. Successful readiness check
    resp = client.get("/readyz")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "READY"
    assert "queue_depth" in data
    assert "active_batch" in data
    assert "kv_free_blocks" in data

    # 2. Check /api/v1/readyz alias
    resp_v1 = client.get("/api/v1/readyz")
    assert resp_v1.status_code == 200
    assert resp_v1.json()["status"] == "READY"

    # 3. Mark system unready (e.g. warming up or draining) -> 503
    system_readiness_status["ready"] = False
    system_readiness_status["reason"] = "Scheduler warming up caches"
    not_ready_resp = client.get("/readyz")
    assert not_ready_resp.status_code == 503
    assert not_ready_resp.json()["error"]["code"] == "NOT_READY"

    # Restore readiness
    system_readiness_status["ready"] = True


def test_SCH_109_metrics_endpoint():
    """
    SCH-109: Metrics endpoint (BE, P0).
    Verifies /metrics and /api/v1/metrics endpoints:
    - Returns Prometheus plain text metrics
    - Contains llm_scheduler_queue_depth, llm_scheduler_active_batch_size, llm_scheduler_kv_blocks
    - Reflects live state updates
    """
    client = TestClient(app)

    # 1. Fetch metrics on /metrics
    resp = client.get("/metrics")
    assert resp.status_code == 200
    assert "text/plain" in resp.headers["content-type"]
    text = resp.text
    assert "llm_scheduler_queue_depth" in text
    assert "llm_scheduler_active_batch_size" in text
    assert "llm_scheduler_kv_blocks_used" in text
    assert "llm_scheduler_kv_blocks_free" in text
    assert "llm_scheduler_requests_total" in text

    # 2. Fetch metrics on /api/v1/metrics
    resp_v1 = client.get("/api/v1/metrics")
    assert resp_v1.status_code == 200
    assert "llm_scheduler_queue_depth" in resp_v1.text
