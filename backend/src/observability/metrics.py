"""
Prometheus Metrics, TTFT, and TPOT Latency Tracking (SCH-112, SCH-117, SCH-118).
"""

from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram, generate_latest, CONTENT_TYPE_LATEST

class SchedulerMetrics:
    def __init__(self, registry: CollectorRegistry = None):
        self.registry = registry or CollectorRegistry(auto_describe=True)

        # SCH-112 Prometheus general metrics
        self.requests_total = Counter(
            "llm_scheduler_requests_total",
            "Total inference requests handled",
            ["model", "status"],
            registry=self.registry
        )
        self.queue_depth = Gauge(
            "llm_scheduler_queue_depth",
            "Current pending requests in queue",
            registry=self.registry
        )
        self.active_batch_size = Gauge(
            "llm_scheduler_active_batch_size",
            "Current active running sequences in batch",
            registry=self.registry
        )
        self.kv_blocks_used = Gauge(
            "llm_scheduler_kv_blocks_used",
            "Currently allocated KV cache blocks",
            registry=self.registry
        )
        self.kv_blocks_free = Gauge(
            "llm_scheduler_kv_blocks_free",
            "Available free KV cache blocks",
            registry=self.registry
        )

        # SCH-117 Time To First Token (TTFT)
        self.ttft_seconds = Histogram(
            "llm_scheduler_ttft_seconds",
            "Time to First Token (TTFT) in seconds from arrival to first token emission",
            ["model"],
            buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
            registry=self.registry
        )

        # SCH-118 Time Per Output Token (TPOT)
        self.tpot_seconds = Histogram(
            "llm_scheduler_tpot_seconds",
            "Time Per Output Token (TPOT) decode step duration in seconds",
            ["model"],
            buckets=(0.005, 0.01, 0.02, 0.05, 0.1, 0.2, 0.5, 1.0),
            registry=self.registry
        )

        # SCH-116 Queue wait-time metrics
        self.queue_wait_seconds = Histogram(
            "llm_scheduler_queue_wait_seconds",
            "Duration in seconds requests spend pending in queue before admission to batch",
            ["model"],
            buckets=(0.001, 0.005, 0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0),
            registry=self.registry
        )

        # SCH-119 End-to-end latency metrics
        self.e2e_latency_seconds = Histogram(
            "llm_scheduler_e2e_latency_seconds",
            "Total end-to-end latency from request arrival to full completion in seconds",
            ["model"],
            buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0),
            registry=self.registry
        )

    def record_request(self, model: str, status: str) -> None:
        self.requests_total.labels(model=model, status=status).inc()

    def update_queue_depth(self, depth: int) -> None:
        self.queue_depth.set(depth)

    def update_batch_size(self, size: int) -> None:
        self.active_batch_size.set(size)

    def update_kv_blocks(self, used: int, free: int) -> None:
        self.kv_blocks_used.set(used)
        self.kv_blocks_free.set(free)

    def record_ttft(self, model: str, duration_seconds: float) -> None:
        self.ttft_seconds.labels(model=model).observe(max(0.0001, duration_seconds))

    def record_tpot(self, model: str, duration_seconds: float) -> None:
        self.tpot_seconds.labels(model=model).observe(max(0.0001, duration_seconds))

    def record_queue_wait(self, model: str, duration_seconds: float) -> None:
        self.queue_wait_seconds.labels(model=model).observe(max(0.0001, duration_seconds))



    def record_e2e_latency(self, model: str, duration_seconds: float) -> None:
        self.e2e_latency_seconds.labels(model=model).observe(max(0.0001, duration_seconds))



    def generate_metrics_text(self) -> str:
        return generate_latest(self.registry).decode("utf-8")

# Singleton instance for app
default_metrics = SchedulerMetrics()
