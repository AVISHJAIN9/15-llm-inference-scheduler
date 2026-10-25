"""
Request Routing, Model-Aware Placement, Least-Loaded Load Balancing, and Replica Draining
(SCH-071, SCH-073, SCH-083).
"""

from enum import Enum
from typing import Dict, List, Optional, Set, Any
from pydantic import BaseModel, Field
from scheduler.models import InferenceRequest

class ReplicaStatus(str, Enum):
    HEALTHY = "HEALTHY"
    UNHEALTHY = "UNHEALTHY"
    DRAINING = "DRAINING"
    DRAINED = "DRAINED"
    OFFLINE = "OFFLINE"


class WorkerReplica(BaseModel):
    worker_id: str
    node_id: str = "node-1"
    endpoint_url: str
    loaded_models: Set[str] = Field(default_factory=set)
    active_requests: int = 0
    active_tokens: int = 0
    gpu_utilization_pct: float = 0.0
    gpu_free_memory_bytes: int = 0
    gpu_temperature_c: float = 40.0
    queue_length: int = 0
    avg_latency_ms: float = 0.0
    ewma_ttft_ms: float = 0.0
    ewma_itl_ms: float = 0.0
    ewma_latency_ms: float = 0.0
    alpha: float = 0.2
    status: ReplicaStatus = ReplicaStatus.HEALTHY

    def record_latency(self, ttft_ms: float, itl_ms: float) -> None:
        """
        Record latency sample with exponential moving average decay (SCH-075).
        """
        latency_sample = ttft_ms + itl_ms
        if self.ewma_latency_ms == 0.0:
            self.ewma_latency_ms = latency_sample
            self.ewma_ttft_ms = ttft_ms
            self.ewma_itl_ms = itl_ms
        else:
            self.ewma_latency_ms = (self.alpha * latency_sample) + ((1.0 - self.alpha) * self.ewma_latency_ms)
            self.ewma_ttft_ms = (self.alpha * ttft_ms) + ((1.0 - self.alpha) * self.ewma_ttft_ms)
            self.ewma_itl_ms = (self.alpha * itl_ms) + ((1.0 - self.alpha) * self.ewma_itl_ms)
        self.avg_latency_ms = self.ewma_latency_ms


class RequestRouter:
    """
    Router implementing:
    - Model-aware routing (SCH-071)
    - Least-loaded routing (SCH-073)
    - Graceful replica draining (SCH-083)
    """
    def __init__(self):
        self._replicas: Dict[str, WorkerReplica] = {}
        self._consecutive_failures: Dict[str, int] = {}
        self._consecutive_successes: Dict[str, int] = {}

    def record_health_probe(
        self,
        worker_id: str,
        success: bool,
        latency_ms: float = 0.0,
        failure_threshold: int = 3,
        success_threshold: int = 2
    ) -> Optional[ReplicaStatus]:
        """
        Record health probe result and transition replica status (SCH-082).
        """
        rep = self._replicas.get(worker_id)
        if not rep:
            return None

        if success:
            self._consecutive_failures[worker_id] = 0
            self._consecutive_successes[worker_id] = self._consecutive_successes.get(worker_id, 0) + 1
            if rep.status in (ReplicaStatus.UNHEALTHY, ReplicaStatus.OFFLINE):
                if self._consecutive_successes[worker_id] >= success_threshold:
                    rep.status = ReplicaStatus.HEALTHY
            else:
                rep.status = ReplicaStatus.HEALTHY

            if latency_ms > 0:
                rep.record_latency(ttft_ms=latency_ms / 2.0, itl_ms=latency_ms / 2.0)
        else:
            self._consecutive_successes[worker_id] = 0
            self._consecutive_failures[worker_id] = self._consecutive_failures.get(worker_id, 0) + 1
            if self._consecutive_failures[worker_id] >= failure_threshold:
                rep.status = ReplicaStatus.OFFLINE
            else:
                rep.status = ReplicaStatus.UNHEALTHY



        return rep.status


    def register_replica(self, replica: WorkerReplica) -> None:
        self._replicas[replica.worker_id] = replica

    def get_replica(self, worker_id: str) -> Optional[WorkerReplica]:
        return self._replicas.get(worker_id)

    def list_replicas(self) -> List[WorkerReplica]:
        return list(self._replicas.values())

    def update_load(self, worker_id: str, delta_requests: int, delta_tokens: int = 0) -> None:
        rep = self._replicas.get(worker_id)
        if rep:
            rep.active_requests = max(0, rep.active_requests + delta_requests)
            rep.active_tokens = max(0, rep.active_tokens + delta_tokens)
            if rep.status == ReplicaStatus.DRAINING and rep.active_requests == 0:
                rep.status = ReplicaStatus.DRAINED

    def drain_replica(self, worker_id: str) -> bool:
        """
        Marks a replica for draining (SCH-083).
        Stops routing new requests to it immediately.
        If it already has 0 active requests, marks DRAINED immediately.
        """
        rep = self._replicas.get(worker_id)
        if not rep:
            return False
        if rep.active_requests == 0:
            rep.status = ReplicaStatus.DRAINED
        else:
            rep.status = ReplicaStatus.DRAINING
        return True

    def route_request(self, request: InferenceRequest) -> Optional[WorkerReplica]:
        """
        Routes request to the optimal worker replica (SCH-071, SCH-073, SCH-083):
        1. Filters only HEALTHY replicas (excludes DRAINING, DRAINED, OFFLINE)
        2. Filters replicas that have request.model_name loaded (SCH-071)
        3. Selects replica with lowest load (active_requests, then active_tokens) (SCH-073)
        """
        candidates = [
            r for r in self._replicas.values()
            if r.status == ReplicaStatus.HEALTHY
            and request.model_name in r.loaded_models
        ]

        if not candidates:
            return None

        # Least-loaded selection: primary key active_requests, secondary active_tokens
        best = min(candidates, key=lambda r: (r.active_requests, r.active_tokens))
        return best

    def route_gpu_aware(
        self,
        request: InferenceRequest,
        min_free_memory_bytes: int = 0,
        max_gpu_utilization_pct: float = 95.0,
        max_temperature_c: float = 85.0
    ) -> Optional[WorkerReplica]:
        """
        Routes requests based on real-time GPU metrics (SCH-072):
        - Filters replicas that are HEALTHY and have the model loaded
        - Enforces thermal safety threshold (gpu_temperature_c < max_temperature_c)
        - Enforces memory headroom requirement (gpu_free_memory_bytes >= min_free_memory_bytes)
        - Enforces maximum GPU utilization (gpu_utilization_pct <= max_gpu_utilization_pct)
        - Selects the candidate with lowest GPU utilization, breaking ties by highest free memory
        """
        candidates = [
            r for r in self._replicas.values()
            if r.status == ReplicaStatus.HEALTHY
            and request.model_name in r.loaded_models
            and r.gpu_temperature_c < max_temperature_c
            and r.gpu_free_memory_bytes >= min_free_memory_bytes
            and r.gpu_utilization_pct <= max_gpu_utilization_pct
        ]

        if not candidates:
            return None

        return min(candidates, key=lambda r: (r.gpu_utilization_pct, -r.gpu_free_memory_bytes))

    def route_queue_length(
        self,
        request: InferenceRequest,
        max_queue_depth: int = 100
    ) -> Optional[WorkerReplica]:
        """
        Routes requests based on queue depth (SCH-074):
        - Filters replicas that are HEALTHY and have the model loaded
        - Filters replicas with queue_length < max_queue_depth (sheds if all exceed threshold)
        - Selects the candidate with lowest queue_length, breaking ties by active_requests
        """
        candidates = [
            r for r in self._replicas.values()
            if r.status == ReplicaStatus.HEALTHY
            and request.model_name in r.loaded_models
            and r.queue_length < max_queue_depth
        ]

        if not candidates:
            return None

        return min(candidates, key=lambda r: (r.queue_length, r.active_requests))

    def route_latency_aware(
        self,
        request: InferenceRequest,
        max_acceptable_latency_ms: float = 5000.0
    ) -> Optional[WorkerReplica]:
        """
        Routes requests based on EWMA latency (SCH-075):
        - Filters replicas that are HEALTHY and have the model loaded
        - Filters replicas with ewma_latency_ms <= max_acceptable_latency_ms (or 0.0 uninitialized)
        - Selects the candidate with lowest ewma_latency_ms, breaking ties by active_requests
        """
        candidates = [
            r for r in self._replicas.values()
            if r.status == ReplicaStatus.HEALTHY
            and request.model_name in r.loaded_models
            and (r.ewma_latency_ms <= max_acceptable_latency_ms or r.ewma_latency_ms == 0.0)
        ]

        if not candidates:
            return None

        return min(candidates, key=lambda r: (r.ewma_latency_ms if r.ewma_latency_ms > 0 else 0.001, r.active_requests))

    def failover_request(
        self,
        request: InferenceRequest,
        failed_worker_id: str,
        reason: str = "worker_failure"
    ) -> Optional[WorkerReplica]:
        """
        Fails over an in-flight request from a failed worker to another healthy replica (SCH-084).
        - Decrements active load on failed worker (or marks it UNHEALTHY if healthy)
        - Finds candidate healthy replicas supporting request.model_name, excluding failed_worker_id
        - Selects least loaded replica
        - Increments load on newly assigned replica
        - Attaches failover metadata to request
        """
        failed_rep = self._replicas.get(failed_worker_id)
        if failed_rep:
            failed_rep.active_requests = max(0, failed_rep.active_requests - 1)
            if failed_rep.status == ReplicaStatus.HEALTHY:
                failed_rep.status = ReplicaStatus.UNHEALTHY

        candidates = [
            r for r in self._replicas.values()
            if r.status == ReplicaStatus.HEALTHY
            and r.worker_id != failed_worker_id
            and request.model_name in r.loaded_models
        ]
        if not candidates:
            return None

        new_rep = min(candidates, key=lambda r: (r.active_requests, r.active_tokens))
        new_rep.active_requests += 1

        request.assigned_worker_id = new_rep.worker_id
        if "failover_history" not in request.metadata:
            request.metadata["failover_history"] = []


        request.metadata["failover_history"].append({
            "from_worker": failed_worker_id,
            "to_worker": new_rep.worker_id,
            "reason": reason
        })

        return new_rep











