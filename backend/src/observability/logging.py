"""
Structured JSON Logging (SCH-114).
Provides JSON formatted structured logging with contextual metadata.
"""

import json
import logging
import sys
import time
from typing import Any, Dict, Optional


class JSONFormatter(logging.Formatter):
    """Formats log records as single-line JSON objects."""

    def __init__(self, service: str = "llm-inference-scheduler"):
        super().__init__()
        self.service = service

    def format(self, record: logging.LogRecord) -> str:
        log_entry: Dict[str, Any] = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(record.created)),
            "level": record.levelname,
            "service": self.service,
            "logger": record.name,
            "message": record.getMessage()
        }

        # Include structured context passed via extra
        extra_fields = getattr(record, "extra_fields", {})
        if extra_fields:
            log_entry.update(extra_fields)



        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_entry)


class StructuredLogger:
    """Wrapper around standard logger to emit structured JSON logs."""

    def __init__(self, name: str = "llm_scheduler", service: str = "llm-inference-scheduler"):
        self.logger = logging.getLogger(name)
        self.logger.setLevel(logging.INFO)
        self.logger.propagate = False

        # Add JSON handler if not already present
        if not self.logger.handlers:
            handler = logging.StreamHandler(sys.stdout)
            handler.setFormatter(JSONFormatter(service=service))
            self.logger.addHandler(handler)

    def log(self, level: int, msg: str, **kwargs: Any) -> None:
        extra = {"extra_fields": kwargs}
        self.logger.log(level, msg, extra=extra)

    def info(self, msg: str, **kwargs: Any) -> None:
        self.log(logging.INFO, msg, **kwargs)

    def warning(self, msg: str, **kwargs: Any) -> None:
        self.log(logging.WARNING, msg, **kwargs)

    def error(self, msg: str, **kwargs: Any) -> None:
        self.log(logging.ERROR, msg, **kwargs)

    def debug(self, msg: str, **kwargs: Any) -> None:
        self.log(logging.DEBUG, msg, **kwargs)


default_logger = StructuredLogger()
