"""
Shared distributed queue coordination (SCH-087).
Coordinates work items across multiple scheduler replicas with lease-based claiming,
acknowledgment, and automatic lease expiration recovery.
"""

import uuid
from typing import Dict, List, Optional, Tuple, Set
from pydantic import BaseModel, Field
from clock import Clock
from scheduler.models import InferenceRequest, RequestStatus

class QueueLease(BaseModel):
    lease_id: str
    request: InferenceRequest
    scheduler_id: str
    acquired_at: float
    expires_at: float

class SharedQueueCoordinator:
    """
    Coordinates shared queue operations across distributed scheduler replicas (SCH-087).
    """
    def __init__(self, clock: Optional[Clock] = None):
        self.clock = clock or Clock()
        self._pending: List[InferenceRequest] = []
        self._active_leases: Dict[str, QueueLease] = {}  # lease_id -> QueueLease
        self._completed_ids: Set[str] = set()

    def enqueue(self, request: InferenceRequest) -> bool:
        """Pushes request into the pending shared queue."""
        if request.request_id in self._completed_ids:
            return False
        request.status = RequestStatus.QUEUED
        self._pending.append(request)
        # Sort by priority desc, arrival_time asc
        self._pending.sort(key=lambda r: (-r.priority, r.arrival_time))
        return True

    def pending_count(self) -> int:
        return len(self._pending)

    def is_completed(self, request_id: str) -> bool:
        return request_id in self._completed_ids

    def claim_request(
        self,
        scheduler_id: str,
        lease_ttl: float = 5.0
    ) -> Optional[Tuple[InferenceRequest, str]]:
        """
        Safely claims the highest-priority pending request with a lease.
        Returns (request, lease_id) or None if queue is empty.
        """
        if not self._pending:
            return None

        req = self._pending.pop(0)
        now = self.clock.now()
        lease_id = f"lease-{uuid.uuid4().hex[:8]}"

        lease = QueueLease(
            lease_id=lease_id,
            request=req,
            scheduler_id=scheduler_id,
            acquired_at=now,
            expires_at=now + lease_ttl
        )
        self._active_leases[lease_id] = lease
        req.status = RequestStatus.IN_FLIGHT
        return req, lease_id

    def renew_lease(self, lease_id: str, additional_ttl: float = 5.0) -> bool:
        """Renews an active unexpired lease."""
        lease = self._active_leases.get(lease_id)
        if not lease:
            return False
        now = self.clock.now()
        if now >= lease.expires_at:
            return False  # Already expired

        lease.expires_at = now + additional_ttl
        return True

    def ack(self, lease_id: str) -> bool:
        """
        Acknowledges successful completion of leased request.
        Fails if lease expired.
        """
        lease = self._active_leases.get(lease_id)
        if not lease:
            return False
        now = self.clock.now()
        if now >= lease.expires_at:
            return False



        self._active_leases.pop(lease_id)
        self._completed_ids.add(lease.request.request_id)
        lease.request.status = RequestStatus.COMPLETED
        return True

    def nack(self, lease_id: str, requeue: bool = True) -> bool:
        """
        Negative acknowledgment: releases claim. If requeue is True, re-enqueues item.
        """
        lease = self._active_leases.pop(lease_id, None)
        if not lease:
            return False

        if requeue:
            self.enqueue(lease.request)
        else:
            lease.request.status = RequestStatus.REJECTED

        return True

    def reclaim_expired_leases(self) -> int:
        """
        Reclaims all leases whose expires_at is past clock.now().
        Re-enqueues the uncompleted requests into the pending pool.
        """
        now = self.clock.now()
        expired_lease_ids = [
            l_id for l_id, l in self._active_leases.items()
            if now >= l.expires_at
        ]

        count = 0
        for l_id in expired_lease_ids:
            lease = self._active_leases.pop(l_id)
            self.enqueue(lease.request)
            count += 1

        return count
