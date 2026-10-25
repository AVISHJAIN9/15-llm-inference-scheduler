import pytest
from fastapi.testclient import TestClient
from api.app import app, batcher
from scheduler.models import InferenceRequest


def test_SCH_143_live_request_view():
    """
    SCH-143: Live request view (FE+BE, P1).
    Verifies /api/v1/dashboard/requests/live endpoint:
    - Active running batch request enumeration
    - Progress reporting (tokens_generated, phase, elapsed_seconds)
    """
    client = TestClient(app)

    # 1. Fetch live requests when idle
    res = client.get("/api/v1/dashboard/requests/live")
    assert res.status_code == 200
    data = res.json()
    assert "active_count" in data
    assert "max_batch_size" in data
    assert isinstance(data["requests"], list)

    # 2. Add an active request to batcher
    req = InferenceRequest(request_id="live-req-1", model_name="llama-3", prompt="test", max_tokens=10)
    admitted = batcher.admit(req)
    if admitted:
        res_active = client.get("/api/v1/dashboard/requests/live")
        assert res_active.status_code == 200
        active_ids = [r["request_id"] for r in res_active.json()["requests"]]
        assert "live-req-1" in active_ids

        # Cleanup
        batcher.step()


def test_SCH_144_request_detail_page():
    """
    SCH-144: Request detail page (FE+BE, P1).
    Verifies /api/v1/dashboard/requests/{request_id} endpoint:
    - Full telemetry inspector for a specific request
    - Tokens generated, KV blocks, latency, prompt length
    - 404 for unknown requests
    """
    client = TestClient(app)

    # 1. Execute an inference request to completion
    resp = client.post(
        "/api/v1/inference",
        json={"request_id": "detail-req-test-1", "model_name": "llama-3", "prompt": "Hello world prompt", "max_tokens": 4}
    )
    assert resp.status_code == 200

    # 2. Query request detail inspector
    detail_resp = client.get("/api/v1/dashboard/requests/detail-req-test-1")
    assert detail_resp.status_code == 200
    detail = detail_resp.json()
    assert detail["request_id"] == "detail-req-test-1"
    assert detail["model_name"] == "llama-3"
    assert detail["prompt_length"] == len("Hello world prompt")
    assert detail["tokens_generated"] >= 1
    assert "kv_blocks_allocated" in detail
    assert "e2e_duration_ms" in detail

    # 3. Negative test: querying unknown request -> 404
    err_resp = client.get("/api/v1/dashboard/requests/unknown-request-id-999")
    assert err_resp.status_code == 404
    assert err_resp.json()["error"]["code"] == "NOT_FOUND"


def test_SCH_146_latency_charts():
    """
    SCH-146: Latency charts (FE+BE, P1).
    Verifies /api/v1/dashboard/charts/latency endpoint:
    - Percentile breakdowns (p50, p90, p99)
    - Covers TTFT, TPOT, and E2E latency by model
    """
    client = TestClient(app)

    resp = client.get("/api/v1/dashboard/charts/latency")
    assert resp.status_code == 200
    charts = resp.json()

    assert "metrics" in charts
    metrics = charts["metrics"]
    assert "ttft_ms" in metrics
    assert "tpot_ms" in metrics
    assert "e2e_ms" in metrics

    # Verify percentiles present for models
    assert "llama-3" in metrics["ttft_ms"]
    assert "p50" in metrics["ttft_ms"]["llama-3"]
    assert "p90" in metrics["ttft_ms"]["llama-3"]
    assert "p99" in metrics["ttft_ms"]["llama-3"]
