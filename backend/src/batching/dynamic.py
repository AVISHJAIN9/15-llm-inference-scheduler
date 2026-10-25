"""
Dynamic Batching Engine and Batch Formation Window (SCH-058, SCH-060).
Dynamically forms batches from queue based on traffic load, batch windows, and priority.
"""

import uuid
from typing import List, Optional, Dict, Any
from pydantic import BaseModel
from scheduler.models import InferenceRequest, RequestStatus
from clock import Clock


class DynamicBatch(BaseModel):
    batch_id: str
    requests: List[InferenceRequest]
    batch_size: int
    formed_at: float


class DynamicBatcher:
    def __init__(
        self,
        max_batch_size: int = 8,
        min_batch_size: int = 1,
        max_wait_ms: float = 0.0,
        clock: Optional[Clock] = None
    ):
        if max_batch_size <= 0:
            raise ValueError("max_batch_size must be positive")
        if min_batch_size <= 0:
            raise ValueError("min_batch_size must be positive")

        self.max_batch_size = max_batch_size
        self.min_batch_size = min_batch_size
        self.max_wait_ms = max_wait_ms
        self.clock = clock or Clock()
        self._pending_queue: List[InferenceRequest] = []

    def enqueue(self, request: InferenceRequest) -> None:
        """Enqueues an admitted request into the batcher queue (SCH-058)."""
        if request.arrival_time <= 0:
            request.arrival_time = self.clock.now()
        request.status = RequestStatus.QUEUED
        self._pending_queue.append(request)

    def has_pending_requests(self) -> bool:
        return len(self._pending_queue) > 0

    @property
    def queue_size(self) -> int:
        return len(self._pending_queue)

    def form_batch(self, force: bool = False) -> Optional[DynamicBatch]:
        """
        Dynamically forms a batch of requests (SCH-058).
        If max_wait_ms is set, checks formation window timeout before forming batch (SCH-060).
        """
        if not self._pending_queue:
            return None

        # Check formation window condition (SCH-060)
        if self.max_wait_ms > 0 and not force:
            now = self.clock.now()
            earliest_arrival = min(r.arrival_time for r in self._pending_queue)
            wait_elapsed_ms = (now - earliest_arrival) * 1000.0

            # Only form batch if max_batch_size reached OR formation window expired
            if len(self._pending_queue) < self.max_batch_size and wait_elapsed_ms < self.max_wait_ms:
                return None

        # Sort pending by priority (descending), then arrival_time (FIFO)
        self._pending_queue.sort(key=lambda r: (-r.priority, r.arrival_time))

        batch_requests = self._pending_queue[:self.max_batch_size]
        self._pending_queue = self._pending_queue[self.max_batch_size:]

        now = self.clock.now()
        for r in batch_requests:
            r.status = RequestStatus.IN_FLIGHT

        batch_id = f"batch-{uuid.uuid4().hex[:12]}"
        return DynamicBatch(
            batch_id=batch_id,
            requests=batch_requests,
            batch_size=len(batch_requests),
            formed_at=now
        )
