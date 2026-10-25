"""
Dispatch coordination, deduplication table, and effectively-once dispatch semantics
(SCH-096, SCH-098).
Guarantees a request is never simultaneously dispatched to multiple workers,
and strictly rejects duplicate or deposed-leader dispatch attempts.
"""

from typing import Dict, Optional, Tuple
from pydantic import BaseModel
from clock import Clock

class DispatchRecord(BaseModel):
    request_id: str
    worker_id: str
    fencing_token: int
    dispatched_at: float
    is_completed: bool = False

class DispatchCoordinator:
    """
    Dispatch Coordinator (SCH-096, SCH-098).
    Enforces duplicate dispatch prevention and effectively-once dispatch invariants.
    """
    def __init__(self, clock: Optional[Clock] = None):
        self.clock = clock or Clock()
        self._dispatches: Dict[str, DispatchRecord] = {}
        self._highest_fencing_token_seen: int = 0

    def dispatch(
        self,
        request_id: str,
        worker_id: str,
        fencing_token: int
    ) -> Tuple[bool, str]:
        """
        Attempts to dispatch request_id to worker_id under leader fencing_token.
        Returns (success, reason).
        """
        # Rule 1: Fencing token check - reject stale or deposed leader writes
        if fencing_token < self._highest_fencing_token_seen:
            return False, f"Stale fencing token {fencing_token} < {self._highest_fencing_token_seen}"

        self._highest_fencing_token_seen = max(self._highest_fencing_token_seen, fencing_token)

        # Rule 2: Duplicate dispatch prevention (SCH-098)
        existing = self._dispatches.get(request_id)
        if existing:
            if not existing.is_completed:
                return False, f"Request {request_id} is already in-flight on worker {existing.worker_id}"
            else:
                return False, f"Request {request_id} has already been completed"

        # Record fresh dispatch
        rec = DispatchRecord(
            request_id=request_id,
            worker_id=worker_id,
            fencing_token=fencing_token,
            dispatched_at=self.clock.now(),
            is_completed=False
        )
        self._dispatches[request_id] = rec
        return True, "Dispatched successfully"

    def complete_dispatch(self, request_id: str, worker_id: str) -> bool:
        rec = self._dispatches.get(request_id)
        if not rec:
            return False
        if rec.worker_id != worker_id:
            return False
        rec.is_completed = True
        return True

    def get_dispatch(self, request_id: str) -> Optional[DispatchRecord]:
        return self._dispatches.get(request_id)

    def is_in_flight(self, request_id: str) -> bool:
        rec = self._dispatches.get(request_id)
        return rec is not None and not rec.is_completed
