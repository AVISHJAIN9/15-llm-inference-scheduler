"""
Scheduler state recovery after crash (SCH-095).
Enforces Invariant P15 §9: "scheduler state recovery after crash yields zero lost and zero duplicated requests".
Recovers pending queue, reconciles in-flight dispatches, and prevents duplicate completions.
"""

from typing import Dict, List, Set, Optional, Tuple, Any
from pydantic import BaseModel, Field
from clock import Clock
from scheduler.models import InferenceRequest, RequestStatus


class RecoveryAuditReport(BaseModel):
    total_submitted: int
    recovered_queued: int
    recovered_in_flight: int
    recovered_completed: int
    zero_lost: bool
    zero_duplicated: bool


class SchedulerStateRecoveryManager:
    """
    Manages crash state recovery and reconciliation for distributed scheduler (SCH-095).
    """
    def __init__(self, clock: Optional[Clock] = None):
        self.clock = clock or Clock()
        self._all_submitted: Dict[str, InferenceRequest] = {}
        self._pending_queue: List[InferenceRequest] = []
        self._in_flight: Dict[str, Tuple[InferenceRequest, str, float]] = {}  # req_id -> (req, worker_id, dispatch_time)
        self._completed: Dict[str, InferenceRequest] = {}

    def submit_request(self, request: InferenceRequest) -> None:
        """Submits a request to the scheduler state."""
        request.status = RequestStatus.QUEUED
        self._all_submitted[request.request_id] = request
        self._pending_queue.append(request)

    def dispatch_request(self, request_id: str, worker_id: str) -> Optional[InferenceRequest]:
        """Dispatches request from queue to worker."""
        for i, req in enumerate(self._pending_queue):
            if req.request_id == request_id:
                self._pending_queue.pop(i)
                req.status = RequestStatus.IN_FLIGHT
                req.assigned_worker_id = worker_id
                self._in_flight[request_id] = (req, worker_id, self.clock.now())
                return req
        return None

    def acknowledge_completion(self, request_id: str) -> bool:
        """Acknowledges request completion from worker before any crash."""
        if request_id in self._in_flight:
            req, _, _ = self._in_flight.pop(request_id)
            req.status = RequestStatus.COMPLETED
            self._completed[request_id] = req
            return True
        return False

    def recover_after_crash(
        self,
        active_worker_ids: Set[str],
        unreachable_worker_ids: Set[str]
    ) -> RecoveryAuditReport:
        """
        Executes state recovery after scheduler/worker crash (SCH-095).
        Invariant: zero lost requests and zero duplicated requests.
        """
        requeued_count = 0
        still_in_flight_count = 0

        # Reconcile in-flight requests:
        # If worker is unreachable, in-flight work must be re-queued without duplicate processing
        in_flight_items = list(self._in_flight.items())
        for req_id, (req, worker_id, disp_time) in in_flight_items:
            if worker_id in unreachable_worker_ids:
                # Worker crashed/unreachable: re-queue request
                self._in_flight.pop(req_id, None)
                req.status = RequestStatus.QUEUED
                req.assigned_worker_id = None
                self._pending_queue.append(req)
                requeued_count += 1
            elif worker_id in active_worker_ids:
                # Worker alive and confirmed executing: preserve in-flight
                still_in_flight_count += 1

        total_submitted = len(self._all_submitted)
        total_accounted = len(self._pending_queue) + len(self._in_flight) + len(self._completed)

        # Invariant checks:
        # Zero lost: total_accounted == total_submitted
        zero_lost = (total_accounted == total_submitted)

        # Zero duplicated: disjoint sets of request IDs across pending, in_flight, completed
        pending_ids = set(r.request_id for r in self._pending_queue)
        in_flight_ids = set(self._in_flight.keys())
        completed_ids = set(self._completed.keys())

        zero_duplicated = (
            len(pending_ids.intersection(in_flight_ids)) == 0
            and len(pending_ids.intersection(completed_ids)) == 0
            and len(in_flight_ids.intersection(completed_ids)) == 0
        )

        return RecoveryAuditReport(
            total_submitted=total_submitted,
            recovered_queued=len(self._pending_queue),
            recovered_in_flight=len(self._in_flight),
            recovered_completed=len(self._completed),
            zero_lost=zero_lost,
            zero_duplicated=zero_duplicated
        )

    def get_pending_queue(self) -> List[InferenceRequest]:
        return list(self._pending_queue)
