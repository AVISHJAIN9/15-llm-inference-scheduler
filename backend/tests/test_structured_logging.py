import pytest
import io
import json
import logging
from observability.logging import StructuredLogger, JSONFormatter

def test_SCH_114_structured_logs():
    """
    SCH-114: Structured logs (BE, P0).
    Provides JSON formatted structured logging with contextual metadata:
    timestamp, log level, service identifier, message, and arbitrary contextual keys.
    """
    # Create an in-memory stream handler to capture log output
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JSONFormatter(service="test-inference-service"))

    logger = StructuredLogger(name="test_logger", service="test-inference-service")
    logger.logger.handlers = [handler]

    # 1. Log an INFO event with structured context
    logger.info(
        "Request admitted to queue",
        request_id="req-struct-1",
        tenant_id="tenant-alpha",
        model_name="llama-3-8b",
        queue_depth=5
    )

    output = stream.getvalue().strip()
    assert output != ""
    log_obj = json.loads(output)

    assert log_obj["level"] == "INFO"
    assert log_obj["service"] == "test-inference-service"
    assert log_obj["message"] == "Request admitted to queue"
    assert log_obj["request_id"] == "req-struct-1"
    assert log_obj["tenant_id"] == "tenant-alpha"
    assert log_obj["model_name"] == "llama-3-8b"
    assert log_obj["queue_depth"] == 5
    assert "timestamp" in log_obj

    # 2. Log an ERROR event with exception details
    stream.truncate(0)
    stream.seek(0)

    try:
        raise ValueError("Invalid scheduling weight")
    except ValueError:
        logger.logger.error("Failed to parse weight", exc_info=True, extra={"extra_fields": {"request_id": "req-struct-2"}})

    err_output = stream.getvalue().strip()
    err_obj = json.loads(err_output)
    assert err_obj["level"] == "ERROR"
    assert "exception" in err_obj
    assert "ValueError: Invalid scheduling weight" in err_obj["exception"]
