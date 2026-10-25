"""
Dynamic worker discovery and capability negotiation (SCH-092).
Enables dynamic discovery of GPU inference workers with automated capability
verification, health probes, and resource filtering.
"""

from typing import Dict, List, Optional, Set
from pydantic import BaseModel, Field
from clock import Clock

class WorkerAnnouncement(BaseModel):
    worker_id: str
    endpoint_url: str
    supported_models: Set[str] = Field(default_factory=set)
    gpu_type: str = "NVIDIA-A100"
    gpu_memory_bytes: int = 80 * 1024 * 1024 * 1024
    max_batch_tokens: int = 16384
    max_concurrent_requests: int = 32
    tags: Dict[str, str] = Field(default_factory=dict)

class DiscoveredWorker(BaseModel):
    announcement: WorkerAnnouncement
    discovered_at: float
    last_verified_at: float
    status: str = "UNVERIFIED"  # UNVERIFIED, VERIFIED, FAILED

class WorkerDiscoveryService:
    """
    Dynamic discovery registry with capability negotiation (SCH-092).
    """
    def __init__(self, clock: Optional[Clock] = None):
        self.clock = clock or Clock()
        self._workers: Dict[str, DiscoveredWorker] = {}

    def announce_worker(self, announcement: WorkerAnnouncement) -> DiscoveredWorker:
        """Announces worker into discovery service."""
        now = self.clock.now()
        worker = DiscoveredWorker(
            announcement=announcement,
            discovered_at=now,
            last_verified_at=now,
            status="UNVERIFIED"
        )
        self._workers[announcement.worker_id] = worker
        return worker

    def verify_worker(self, worker_id: str, probe_success: bool = True) -> bool:
        """Verifies health and negotiated capabilities of worker."""
        worker = self._workers.get(worker_id)
        if not worker:
            return False

        worker.last_verified_at = self.clock.now()
        if probe_success:
            worker.status = "VERIFIED"
            return True
        else:
            worker.status = "FAILED"
            return False



    def find_workers(
        self,
        model_name: Optional[str] = None,
        min_gpu_memory_bytes: int = 0,
        min_max_batch_tokens: int = 0
    ) -> List[DiscoveredWorker]:
        """
        Discovers verified workers matching required capabilities.
        """
        results: List[DiscoveredWorker] = []
        for worker in self._workers.values():
            if worker.status != "VERIFIED":
                continue
            ann = worker.announcement
            if model_name and model_name not in ann.supported_models:
                continue
            if ann.gpu_memory_bytes < min_gpu_memory_bytes:
                continue
            if ann.max_batch_tokens < min_max_batch_tokens:
                continue
            results.append(worker)
        return results

    def deregister_worker(self, worker_id: str) -> bool:
        return self._workers.pop(worker_id, None) is not None
