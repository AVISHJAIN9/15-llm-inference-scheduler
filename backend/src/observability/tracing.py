"""
OpenTelemetry Tracing Integration (SCH-113).
Provides distributed tracing for scheduler request lifecycles.
"""

from typing import Optional, Dict, Any
from opentelemetry import trace
from opentelemetry.trace import Tracer, Span, StatusCode
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor, SpanExporter
from opentelemetry.sdk.resources import Resource


class SchedulerTracer:
    """Manages OpenTelemetry tracing for the inference scheduler."""

    def __init__(self, service_name: str = "llm-inference-scheduler", exporter: Optional[SpanExporter] = None):
        self.service_name = service_name
        self.resource = Resource.create({"service.name": service_name})
        self.provider = TracerProvider(resource=self.resource)
        self.exporter = exporter
        if self.exporter:
            self.provider.add_span_processor(SimpleSpanProcessor(self.exporter))
        self.tracer: Tracer = self.provider.get_tracer(service_name)

    def start_request_span(
        self,
        request_id: str,
        model_name: str,
        tenant_id: str = "default",
        priority: int = 0,
        parent_context: Optional[Any] = None
    ) -> Span:
        """Starts a root span for an inference request."""
        span = self.tracer.start_span(
            name="inference.request",
            context=parent_context,
            attributes={
                "scheduler.request_id": request_id,
                "scheduler.model_name": model_name,
                "scheduler.tenant_id": tenant_id,
                "scheduler.priority": priority
            }
        )
        return span

    def start_operation_span(
        self,
        operation_name: str,
        request_id: Optional[str] = None,
        attributes: Optional[Dict[str, Any]] = None
    ) -> Span:
        """Starts a child span for a scheduling operation (e.g., admit, enqueue, step)."""
        attrs = attributes or {}
        if request_id:
            attrs["scheduler.request_id"] = request_id
        return self.tracer.start_span(name=f"scheduler.{operation_name}", attributes=attrs)

    def record_exception(self, span: Span, exc: Exception) -> None:
        """Records an exception and marks span status as ERROR."""
        span.record_exception(exc)
        span.set_status(StatusCode.ERROR, str(exc))

    def end_span(self, span: Span, status: str = "OK") -> None:
        """Ends a span with the specified status."""
        if status == "ERROR":
            span.set_status(StatusCode.ERROR)
        else:
            span.set_status(StatusCode.OK)
        span.end()




# Default singleton scheduler tracer
default_tracer = SchedulerTracer()
