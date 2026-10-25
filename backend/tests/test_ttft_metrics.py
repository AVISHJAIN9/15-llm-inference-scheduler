import pytest
from prometheus_client import CollectorRegistry
from observability.metrics import SchedulerMetrics

def test_SCH_117_ttft_metrics():
    registry = CollectorRegistry(auto_describe=True)
    metrics = SchedulerMetrics(registry=registry)

    # Record Time To First Token for llama-3: 120ms (0.12s) and 240ms (0.24s)
    metrics.record_ttft(model="llama-3", duration_seconds=0.12)
    metrics.record_ttft(model="llama-3", duration_seconds=0.24)

    text = metrics.generate_metrics_text()
    assert "llm_scheduler_ttft_seconds_bucket" in text
    assert 'model="llama-3"' in text
    assert "llm_scheduler_ttft_seconds_count" in text
    assert "llm_scheduler_ttft_seconds_sum" in text

    # Verify count is 2
    assert 'llm_scheduler_ttft_seconds_count{model="llama-3"} 2.0' in text
