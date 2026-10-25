import pytest
import time
from fastapi.testclient import TestClient
from prometheus_client import CollectorRegistry
from api.app import app
from observability.metrics import SchedulerMetrics, default_metrics


def test_SCH_116_queue_wait_time_metrics():
    """
    SCH-116: Queue wait-time metrics (BE, P0).
    Verifies:
    - Histogram llm_scheduler_queue_wait_seconds tracks wait time distributions
    - Per-model labeling
    - Accurate observation recording
    """
    registry = CollectorRegistry(auto_describe=True)
    metrics = SchedulerMetrics(registry=registry)

    # Record simulated queue waits
    metrics.record_queue_wait(model="llama-3", duration_seconds=0.015)
    metrics.record_queue_wait(model="llama-3", duration_seconds=0.120)
    metrics.record_queue_wait(model="gpt-2", duration_seconds=0.005)

    metrics_text = metrics.generate_metrics_text()
    assert "llm_scheduler_queue_wait_seconds_count{model=\"llama-3\"} 2.0" in metrics_text
    assert "llm_scheduler_queue_wait_seconds_count{model=\"gpt-2\"} 1.0" in metrics_text
    assert "llm_scheduler_queue_wait_seconds_sum{model=\"llama-3\"}" in metrics_text

    # Also verify via live app client request execution
    client = TestClient(app)
    resp = client.post("/api/v1/inference", json={"model_name": "llama-3", "prompt": "Hi", "max_tokens": 2})
    assert resp.status_code == 200

    prom_resp = client.get("/metrics")
    assert "llm_scheduler_queue_wait_seconds" in prom_resp.text


def test_SCH_119_end_to_end_latency_metrics():
    """
    SCH-119: End-to-end latency metrics (BE, P0).
    Verifies:
    - Histogram llm_scheduler_e2e_latency_seconds tracks total request duration
    - Observed on completion of inference execution
    - Per-model histogram metrics exposed via Prometheus
    """
    registry = CollectorRegistry(auto_describe=True)
    metrics = SchedulerMetrics(registry=registry)

    # Record simulated e2e latencies
    metrics.record_e2e_latency(model="mistral-7b", duration_seconds=0.350)
    metrics.record_e2e_latency(model="mistral-7b", duration_seconds=0.850)

    metrics_text = metrics.generate_metrics_text()
    assert "llm_scheduler_e2e_latency_seconds_count{model=\"mistral-7b\"} 2.0" in metrics_text
    assert "llm_scheduler_e2e_latency_seconds_sum{model=\"mistral-7b\"}" in metrics_text

    # Verify live request completes and updates e2e histogram
    client = TestClient(app)
    resp = client.post("/api/v1/inference", json={"model_name": "gpt-2", "prompt": "Once upon a time", "max_tokens": 4})
    assert resp.status_code == 200

    prom_resp = client.get("/metrics")
    assert "llm_scheduler_e2e_latency_seconds" in prom_resp.text
