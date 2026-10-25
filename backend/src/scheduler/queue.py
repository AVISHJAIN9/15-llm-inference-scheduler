"""
Queue management, FIFO, Priority, Weighted Fair Queue (WFQ), and Queue Aging
(SCH-003, SCH-005, SCH-006, SCH-007, SCH-011).
"""

from collections import deque
import heapq
from typing import Dict, Optional, List, Tuple
from scheduler.models import InferenceRequest, RequestStatus
from clock import Clock

class FIFOQueue:
    def __init__(self, max_capacity: int = 1000):
        self.max_capacity = max_capacity
        self._queue: deque[InferenceRequest] = deque()
        self._index: Dict[str, InferenceRequest] = {}

    def enqueue(self, request: InferenceRequest) -> bool:
        if len(self._queue) >= self.max_capacity:
            return False
        if request.request_id in self._index:
            return False
        request.status = RequestStatus.QUEUED
        self._queue.append(request)
        self._index[request.request_id] = request
        return True

    def dequeue(self) -> Optional[InferenceRequest]:
        if not self._queue:
            return None
        req = self._queue.popleft()
        self._index.pop(req.request_id, None)
        return req

    def peek(self) -> Optional[InferenceRequest]:
        if not self._queue:
            return None
        return self._queue[0]

    def remove(self, request_id: str) -> Optional[InferenceRequest]:
        req = self._index.pop(request_id, None)
        if req:
            self._queue.remove(req)
        return req

    def get(self, request_id: str) -> Optional[InferenceRequest]:
        return self._index.get(request_id)

    def size(self) -> int:
        return len(self._queue)

    def is_empty(self) -> bool:
        return len(self._queue) == 0

    def all_requests(self) -> List[InferenceRequest]:
        return list(self._queue)


class PriorityQueue:
    """
    Priority Queue (SCH-006) with optional dynamic aging (SCH-011).
    Higher priority dequeues first. Equal priority broken by arrival_time (FIFO).
    With aging: effective_priority = base_priority + (now - arrival_time) * aging_rate.
    """
    def __init__(self, max_capacity: int = 1000, aging_rate: float = 0.0, clock: Optional[Clock] = None):
        self.max_capacity = max_capacity
        self.aging_rate = aging_rate
        self.clock = clock or Clock()
        self._items: Dict[str, InferenceRequest] = {}

    def enqueue(self, request: InferenceRequest) -> bool:
        if len(self._items) >= self.max_capacity:
            return False
        if request.request_id in self._items:
            return False
        request.status = RequestStatus.QUEUED
        self._items[request.request_id] = request
        return True

    def _effective_priority(self, req: InferenceRequest, now: float) -> float:
        age = max(0.0, now - req.arrival_time)
        return req.priority + (age * self.aging_rate)

    def peek(self) -> Optional[InferenceRequest]:
        if not self._items:
            return None
        now = self.clock.now()
        # Sort key: (-effective_priority, arrival_time)
        best = min(self._items.values(), key=lambda r: (-self._effective_priority(r, now), r.arrival_time))
        best.effective_priority = self._effective_priority(best, now)
        return best

    def dequeue(self) -> Optional[InferenceRequest]:
        best = self.peek()
        if best:
            del self._items[best.request_id]
        return best

    def remove(self, request_id: str) -> Optional[InferenceRequest]:
        return self._items.pop(request_id, None)

    def get(self, request_id: str) -> Optional[InferenceRequest]:
        return self._items.get(request_id)

    def size(self) -> int:
        return len(self._items)

    def is_empty(self) -> bool:
        return len(self._items) == 0


class WeightedFairQueue:
    """
    Weighted Fair Queue (SCH-007) using Deficit Round Robin (DRR) over tenants/classes.
    Guarantees long-term throughput proportional to assigned weights.
    """
    def __init__(self, quantum: int = 1):
        self.quantum = quantum
        self._queues: Dict[str, deque[InferenceRequest]] = {}
        self._weights: Dict[str, int] = {}
        self._deficits: Dict[str, int] = {}
        self._active_tenants: List[str] = []
        self._index: Dict[str, Tuple[str, InferenceRequest]] = {}

    def set_tenant_weight(self, tenant_id: str, weight: int) -> None:
        if weight <= 0:
            raise ValueError("Weight must be > 0")
        self._weights[tenant_id] = weight
        if tenant_id not in self._deficits:
            self._deficits[tenant_id] = 0

    def enqueue(self, request: InferenceRequest) -> bool:
        tenant_id = request.tenant_id
        if request.request_id in self._index:
            return False
        if tenant_id not in self._weights:
            self._weights[tenant_id] = max(1, request.weight)
            self._deficits[tenant_id] = 0

        if tenant_id not in self._queues:
            self._queues[tenant_id] = deque()

        request.status = RequestStatus.QUEUED
        self._queues[tenant_id].append(request)
        self._index[request.request_id] = (tenant_id, request)

        if tenant_id not in self._active_tenants:
            self._active_tenants.append(tenant_id)
        return True

    def dequeue(self) -> Optional[InferenceRequest]:
        if not self._active_tenants:
            return None

        rounds = 0
        max_rounds = len(self._active_tenants) * 2 + 1
        cost = 1

        while self._active_tenants and rounds < max_rounds:
            tenant = self._active_tenants[0]
            q = self._queues.get(tenant)

            if not q:
                self._active_tenants.pop(0)
                self._deficits[tenant] = 0
                continue

            if self._deficits[tenant] < cost:
                self._deficits[tenant] += self._weights.get(tenant, 1) * self.quantum

            if self._deficits[tenant] >= cost:
                req = q.popleft()
                self._deficits[tenant] -= cost
                self._index.pop(req.request_id, None)

                # If queue is now empty or deficit is spent below cost, rotate to back
                if not q:
                    self._active_tenants.pop(0)
                    self._deficits[tenant] = 0
                elif self._deficits[tenant] < cost:
                    self._active_tenants.pop(0)
                    self._active_tenants.append(tenant)
                # If still has deficit and queue not empty, tenant remains at head for next dequeue
                return req
            else:
                rounds += 1
                self._active_tenants.pop(0)
                self._active_tenants.append(tenant)

        return None

    def remove(self, request_id: str) -> Optional[InferenceRequest]:
        entry = self._index.pop(request_id, None)
        if not entry:
            return None
        tenant_id, req = entry
        q = self._queues.get(tenant_id)
        if q and req in q:
            q.remove(req)
            if not q and tenant_id in self._active_tenants:
                self._active_tenants.remove(tenant_id)
        return req

    def size(self) -> int:
        return len(self._index)

    def is_empty(self) -> bool:
        return len(self._index) == 0


class QueueManager:
    """Manages queue routing, state tracking, and policy-driven queue operations."""
    def __init__(self, fifo_queue: Optional[FIFOQueue] = None):
        self.fifo_queue = fifo_queue or FIFOQueue()

    def submit(self, request: InferenceRequest) -> bool:
        return self.fifo_queue.enqueue(request)

    def pop_next(self) -> Optional[InferenceRequest]:
        return self.fifo_queue.dequeue()

    def cancel(self, request_id: str) -> Optional[InferenceRequest]:
        req = self.fifo_queue.remove(request_id)
        if req:
            req.status = RequestStatus.CANCELLED
        return req

    def depth(self) -> int:
        return self.fifo_queue.size()
