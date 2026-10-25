"""
Worker registration, heartbeats, and cluster node tracking (SCH-090, SCH-091).
"""

from typing import Dict, List, Optional, Set, Any
from pydantic import BaseModel, Field
from clock import Clock

class WorkerMetadata(BaseModel):
    worker_id: str
    endpoint_url: str
    supported_models: Set[str] = Field(default_factory=set)
    gpu_ids: List[str] = Field(default_factory=list)
    max_concurrent_requests: int = 16
    registered_at: float
    last_heartbeat: float
    is_alive: bool = True

class WorkerRegistry:
    """
    Worker registry managing registration and heartbeat liveness tracking (SCH-090, SCH-091).
    """
    def __init__(self, clock: Optional[Clock] = None, heartbeat_timeout: float = 10.0):
        self.clock = clock or Clock()
        self.heartbeat_timeout = heartbeat_timeout
        self._workers: Dict[str, WorkerMetadata] = {}

    def register_worker(
        self,
        worker_id: str,
        endpoint_url: str,
        supported_models: Set[str],
        gpu_ids: Optional[List[str]] = None,
        max_concurrent_requests: int = 16
    ) -> WorkerMetadata:
        """Registers a worker or updates its registration (SCH-090)."""
        now = self.clock.now()
        meta = WorkerMetadata(
            worker_id=worker_id,
            endpoint_url=endpoint_url,
            supported_models=supported_models,
            gpu_ids=gpu_ids or [],
            max_concurrent_requests=max_concurrent_requests,
            registered_at=now,
            last_heartbeat=now,
            is_alive=True
        )
        self._workers[worker_id] = meta
        return meta

    def record_heartbeat(self, worker_id: str) -> bool:
        """Records a heartbeat from worker_id (SCH-091)."""
        worker = self._workers.get(worker_id)
        if not worker:
            return False
        worker.last_heartbeat = self.clock.now()
        worker.is_alive = True
        return True

    def get_worker(self, worker_id: str) -> Optional[WorkerMetadata]:
        return self._workers.get(worker_id)

    def list_healthy_workers(self) -> List[WorkerMetadata]:
        """Returns all workers whose last heartbeat is within heartbeat_timeout (SCH-091)."""
        now = self.clock.now()
        healthy = []
        for w in self._workers.values():
            if now - w.last_heartbeat <= self.heartbeat_timeout:
                w.is_alive = True
                healthy.append(w)
            else:
                w.is_alive = False
        return healthy

    def check_dead_workers(self) -> List[str]:
        """Identifies and returns worker_ids that timed out (SCH-091)."""
        now = self.clock.now()
        dead = []
        for w_id, w in self._workers.items():
            if now - w.last_heartbeat > self.heartbeat_timeout:
                w.is_alive = False
                dead.append(w_id)
        return dead
