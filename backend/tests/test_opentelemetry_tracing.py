import pytest
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import StatusCode
from observability.tracing import SchedulerTracer

def test_SCH_113_opentelemetry_tracing():
    """
    SCH-113: OpenTelemetry tracing (BE, P0).
    Provides distributed tracing for scheduler request lifecycles:
    root request span, operation child spans, exception recording, status codes.
    """
    exporter = InMemorySpanExporter()
    tracer = SchedulerTracer(service_name="test-scheduler", exporter=exporter)

    # 1. Start root request span
    root_span = tracer.start_request_span(
        request_id="req-trace-1",
        model_name="llama-3-8b",
        tenant_id="tenant-gold",
        priority=10
    )
    assert root_span.is_recording()

    # 2. Start child operation span (e.g. admission check)
    child_span = tracer.start_operation_span(
        operation_name="admission_check",
        request_id="req-trace-1",
        attributes={"admission.policy": "TOKEN_BUDGET"}
    )
    tracer.end_span(child_span, status="OK")

    # 3. Start second child operation with error recording
    err_span = tracer.start_operation_span("kv_allocation", request_id="req-trace-1")
    try:
        raise RuntimeError("KV allocation out of memory")
    except RuntimeError as ex:
        tracer.record_exception(err_span, ex)
    tracer.end_span(err_span, status="ERROR")

    # End root span
    tracer.end_span(root_span, status="OK")

    # Verify exported spans
    spans = exporter.get_finished_spans()
    assert len(spans) == 3

    span_names = [s.name for s in spans]
    assert "scheduler.admission_check" in span_names
    assert "scheduler.kv_allocation" in span_names
    assert "inference.request" in span_names

    # Check root attributes
    root_exported = next(s for s in spans if s.name == "inference.request")
    assert root_exported.attributes["scheduler.request_id"] == "req-trace-1"
    assert root_exported.attributes["scheduler.model_name"] == "llama-3-8b"
    assert root_exported.attributes["scheduler.tenant_id"] == "tenant-gold"

    # Check error span attributes & status
    err_exported = next(s for s in spans if s.name == "scheduler.kv_allocation")
    assert err_exported.status.status_code == StatusCode.ERROR
    assert len(err_exported.events) >= 1  # Exception event recorded
