import pytest
from prometheus_client import CollectorRegistry
from observability.metrics import SchedulerMetrics

def test_SCH_118_tpot_metrics():
    registry = CollectorRegistry(auto_describe=True)
    metrics = SchedulerMetrics(registry=registry)

    # Record Time Per Output Token for qwen-0.5b: 25ms (0.025s) and 35ms (0.035s)
    metrics.record_tpot(model="qwen-0.5b", duration_seconds=0.025)
    metrics.record_tpot(model="qwen-0.5b", duration_seconds=0.035)

    text = metrics.generate_metrics_text()
    assert "llm_scheduler_tpot_seconds_bucket" in text
    assert 'model="qwen-0.5b"' in text
    assert "llm_scheduler_tpot_seconds_count" in text
    assert "llm_scheduler_tpot_seconds_sum" in text

    # Verify count is 2
    assert 'llm_scheduler_tpot_seconds_count{model="qwen-0.5b"} 2.0' in text
