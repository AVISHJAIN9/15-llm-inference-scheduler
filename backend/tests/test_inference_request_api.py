import pytest
from fastapi.testclient import TestClient
from api.app import app

def test_SCH_099_inference_request_api():
    client = TestClient(app)

    # Health check
    h = client.get("/healthz")
    assert h.status_code == 200
    assert h.json()["status"] in ("ok", "HEALTHY")

    # Submit valid inference request
    payload = {
        "request_id": "test-sync-1",
        "model_name": "gpt-2",
        "prompt": "The capital of France is",
        "max_tokens": 4
    }
    resp = client.post("/api/v1/inference", json=payload)
    assert resp.status_code == 200
    data = resp.json()

    assert data["request_id"] == "test-sync-1"
    assert data["model_name"] == "gpt-2"
    assert data["status"] == "COMPLETED"
    assert data["tokens_generated"] >= 1
    assert "tok" in data["text"]

    # Negative test: Unknown model rejected by admission controller
    bad_payload = {
        "model_name": "unsupported-model-999",
        "prompt": "hello",
        "max_tokens": 4
    }
    bad_resp = client.post("/api/v1/inference", json=bad_payload)
    assert bad_resp.status_code == 400
    assert bad_resp.json()["error"]["code"] == "ADMISSION_REJECTED"
