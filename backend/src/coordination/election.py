"""
Scheduler leader election, fencing tokens, and lease management (SCH-085, SCH-089).
Guarantees single active leader dispatch with monotonically increasing fencing tokens to reject deposed leader writes.
"""

from typing import Optional, Tuple, Dict, Any
from clock import Clock

class LeaderElector:
    """
    Leader election and lease manager with fencing tokens (SCH-085, SCH-089).
    Invariants:
    1. At most one active leader holds a valid lease at any instant.
    2. Fencing token monotonically increments on every new leader takeover.
    3. Deposed leader writes carrying stale fencing tokens are strictly rejected.
    """
    def __init__(self, clock: Optional[Clock] = None, default_lease_ttl: float = 5.0):
        self.clock = clock or Clock()
        self.default_lease_ttl = default_lease_ttl
        self.current_leader_id: Optional[str] = None
        self.lease_expires_at: float = 0.0
        self.fencing_token: int = 0

    def is_leader(self, candidate_id: str) -> bool:
        now = self.clock.now()
        return self.current_leader_id == candidate_id and now < self.lease_expires_at

    def acquire_or_renew(self, candidate_id: str, lease_ttl: Optional[float] = None) -> Tuple[bool, int]:
        """
        Attempts to acquire or renew leadership.
        Returns (is_leader, fencing_token).
        """
        now = self.clock.now()
        ttl = lease_ttl or self.default_lease_ttl

        # Case 1: Candidate is already active leader -> renew lease, fencing token unchanged
        if self.current_leader_id == candidate_id and now < self.lease_expires_at:
            self.lease_expires_at = now + ttl
            return True, self.fencing_token

        # Case 2: Lease expired or no current leader -> candidate takes over, fencing token increments
        if self.current_leader_id is None or now >= self.lease_expires_at:
            self.current_leader_id = candidate_id
            self.lease_expires_at = now + ttl
            self.fencing_token += 1
            return True, self.fencing_token

        # Case 3: Another active leader holds a valid unexpired lease -> acquisition rejected
        return False, self.fencing_token

    def step_down(self, leader_id: str) -> bool:
        """Voluntary step-down by current leader."""
        if self.current_leader_id == leader_id:
            self.lease_expires_at = self.clock.now()
            self.current_leader_id = None
            return True
        return False

    def validate_write(self, fencing_token: int) -> bool:
        """
        Strict fencing token validation against split-brain / late writes.
        A write is accepted ONLY if its fencing token matches current leader's active token.
        """
        now = self.clock.now()
        if now >= self.lease_expires_at:
            return False  # Lease expired
        return fencing_token == self.fencing_token
