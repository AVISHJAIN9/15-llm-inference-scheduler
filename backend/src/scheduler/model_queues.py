"""
SCH-010: Per-model queues.
Maintains isolated queues per model. Enforces model locality so requests
are only dispatched to workers that have the corresponding model loaded.
"""

from collections import deque
from typing import Dict, List, Optional
from pydantic import BaseModel, Field
from scheduler.models import InferenceRequest, RequestStatus


class WorkerModelCapability(BaseModel):
    worker_id: str
    loaded_models: List[str] = Field(default_factory=list)


class ModelQueueManager:
    def __init__(self):
        self._queues: Dict[str, deque[InferenceRequest]] = {}

    def enqueue(self, req: InferenceRequest) -> None:
        model = req.model_name
        if model not in self._queues:
            self._queues[model] = deque()
        req.status = RequestStatus.QUEUED
        self._queues[model].append(req)

    def get_queue_depth(self, model_name: str) -> int:
        if model_name not in self._queues:
            return 0
        return len(self._queues[model_name])

    def dispatch_for_worker(self, worker: WorkerModelCapability) -> Optional[InferenceRequest]:
        """
        Dispatches the next request matching one of the worker's loaded models.
        Selects the model queue with the oldest arrival time or largest backlog.
        Guarantees that a request NEVER runs on a worker lacking the requested model.
        """
        best_candidate: Optional[InferenceRequest] = None
        best_model: Optional[str] = None

        for model in worker.loaded_models:
            q = self._queues.get(model)
            if q and len(q) > 0:
                head = q[0]
                if best_candidate is None or head.arrival_time < best_candidate.arrival_time:
                    best_candidate = head
                    best_model = model

        if best_model is not None and best_candidate is not None:
            popped = self._queues[best_model].popleft()
            popped.status = RequestStatus.IN_FLIGHT
            popped.assigned_worker_id = worker.worker_id
            return popped

        return None
