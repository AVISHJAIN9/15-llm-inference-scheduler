import pytest
import io
import json
import logging
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import StatusCode

from observability.tracing import SchedulerTracer
from observability.logging import StructuredLogger, JSONFormatter
from observability.decision_log import RequestDecisionLogger, DecisionType


def test_SCH_113_opentelemetry_tracing():
    """
    SCH-113: OpenTelemetry tracing (BE, P0).
    Verifies:
    - Root request span creation with model, priority, and tenant attributes
    - Child operation spans (e.g. admit, batch_step)
    - Exception recording and status transitions
    """
    exporter = InMemorySpanExporter()
    tracer_manager = SchedulerTracer(service_name="test-scheduler", exporter=exporter)

    # 1. Start root request span
    root_span = tracer_manager.start_request_span(
        request_id="req-span-1",
        model_name="llama-3-8b",
        tenant_id="tenant-alpha",
        priority=10
    )
    assert root_span.is_recording()

    # 2. Start child operation span
    child_span = tracer_manager.start_operation_span(
        operation_name="batch_admit",
        request_id="req-span-1",
        attributes={"batch_size": 4}
    )
    tracer_manager.end_span(child_span, status="OK")

    # 3. Record exception on root span and finish
    try:
        raise ValueError("Simulated allocation failure")
    except Exception as exc:
        tracer_manager.record_exception(root_span, exc)
    tracer_manager.end_span(root_span, status="ERROR")

    # 4. Verify exported spans
    spans = exporter.get_finished_spans()
    assert len(spans) == 2

    # Verify child span
    child = next(s for s in spans if s.name == "scheduler.batch_admit")
    assert child.attributes["scheduler.request_id"] == "req-span-1"
    assert child.attributes["batch_size"] == 4
    assert child.status.status_code == StatusCode.OK

    # Verify root span
    root = next(s for s in spans if s.name == "inference.request")
    assert root.attributes["scheduler.request_id"] == "req-span-1"
    assert root.attributes["scheduler.model_name"] == "llama-3-8b"
    assert root.attributes["scheduler.tenant_id"] == "tenant-alpha"
    assert root.attributes["scheduler.priority"] == 10
    assert root.status.status_code == StatusCode.ERROR
    assert len(root.events) >= 1  # Exception event recorded
    assert root.events[0].name == "exception"


def test_SCH_114_structured_logs():
    """
    SCH-114: Structured logs (BE, P0).
    Verifies:
    - Output formatted as valid single-line JSON
    - Includes standard fields: timestamp, level, service, message
    - Contextual metadata serialized into json keys
    - Exception stacktrace formatting
    """
    log_capture = io.StringIO()
    handler = logging.StreamHandler(log_capture)
    handler.setFormatter(JSONFormatter(service="llm-inference-scheduler"))

    logger = StructuredLogger(name="test_logger", service="llm-inference-scheduler")
    logger.logger.handlers = [handler]

    # 1. Info log with context
    logger.info(
        "Request admitted to queue",
        request_id="req-123",
        model_name="llama-3",
        queue_depth=5
    )

    log_output = log_capture.getvalue().strip()
    entry = json.loads(log_output)
    assert entry["level"] == "INFO"
    assert entry["service"] == "llm-inference-scheduler"
    assert entry["message"] == "Request admitted to queue"
    assert entry["request_id"] == "req-123"
    assert entry["model_name"] == "llama-3"
    assert entry["queue_depth"] == 5
    assert "timestamp" in entry

    # 2. Error log with exception
    log_capture.truncate(0)
    log_capture.seek(0)
    try:
        raise RuntimeError("Worker unreachable")
    except Exception:
        logger.logger.error("Dispatch failure", exc_info=True, extra={"extra_fields": {"worker_id": "w-1"}})

    err_output = log_capture.getvalue().strip()
    err_entry = json.loads(err_output)
    assert err_entry["level"] == "ERROR"
    assert "Worker unreachable" in err_entry["exception"]
    assert err_entry["worker_id"] == "w-1"


def test_SCH_115_request_decision_logs_redaction():
    """
    SCH-115: Request decision logs (BE, P0).
    Verifies:
    - Decisions (ADMITTED, QUEUED, REJECTED, etc.) recorded with telemetry
    - §9 Invariant: Strict prompt redaction (raw prompt never appears in records or logs)
    """
    d_logger = RequestDecisionLogger(max_history=50)
    d_logger.clear()

    sensitive_prompt = "TOP_SECRET_PROMPT_WITH_PII_AND_CREDIT_CARD_4111_2222_3333_4444"

    # 1. Record decision with raw prompt passed
    rec = d_logger.record_decision(
        request_id="req-dec-1",
        tenant_id="tenant-bank",
        model_name="mistral-7b",
        decision=DecisionType.ADMITTED,
        reason="Headroom available",
        queue_depth=2,
        active_batch_size=4,
        kv_free_blocks=120,
        prompt=sensitive_prompt
    )

    # 2. Verify record attributes
    assert rec.request_id == "req-dec-1"
    assert rec.decision == DecisionType.ADMITTED
    assert rec.prompt_length == len(sensitive_prompt)
    assert rec.prompt_redacted is True

    # 3. Verify serialized records contain zero raw prompt text
    stored_records = d_logger.get_records()
    assert len(stored_records) == 1
    rec_dict = stored_records[0]
    assert "prompt" not in rec_dict or rec_dict.get("prompt") == "[REDACTED]"
    json_dump = json.dumps(stored_records)
    assert sensitive_prompt not in json_dump

    # 4. Grep string verification (§9 invariant adversarial check)
    assert "TOP_SECRET" not in json_dump
    assert "4111" not in json_dump
