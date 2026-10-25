"""
Distributed scheduler state synchronization (SCH-086).
Maintains versioned state snapshots across leader and follower scheduler instances
with fencing token validation to ensure consensus and prevent split-brain states.
"""

from typing import Dict, List, Any, Optional
from pydantic import BaseModel, Field
from clock import Clock

class SchedulerStateSnapshot(BaseModel):
    version: int
    leader_id: str
    fencing_token: int
    timestamp: float
    queue_requests: List[Dict[str, Any]] = Field(default_factory=list)
    active_workers: List[Dict[str, Any]] = Field(default_factory=list)
    dispatches: Dict[str, Dict[str, Any]] = Field(default_factory=dict)

class DistributedStateManager:
    """
    Coordinates distributed state management and replication across leader/followers (SCH-086).
    """
    def __init__(self, node_id: str, clock: Optional[Clock] = None):
        self.node_id = node_id
        self.clock = clock or Clock()
        self.current_version = 0
        self.latest_fencing_token = 0
        self.state: Dict[str, Any] = {
            "queue_requests": [],
            "active_workers": [],
            "dispatches": {}
        }

    def publish_snapshot(
        self,
        leader_id: str,
        fencing_token: int,
        queue_requests: List[Dict[str, Any]],
        active_workers: List[Dict[str, Any]],
        dispatches: Dict[str, Dict[str, Any]]
    ) -> SchedulerStateSnapshot:
        """
        Publishes a new versioned state snapshot from the active leader.
        Rejects stale writes if fencing_token < latest_fencing_token.
        """
        if fencing_token < self.latest_fencing_token:
            raise ValueError(f"Stale fencing token {fencing_token} < {self.latest_fencing_token}")



        self.current_version += 1
        self.latest_fencing_token = fencing_token
        self.state["queue_requests"] = list(queue_requests)
        self.state["active_workers"] = list(active_workers)
        self.state["dispatches"] = dict(dispatches)

        return SchedulerStateSnapshot(
            version=self.current_version,
            leader_id=leader_id,
            fencing_token=fencing_token,
            timestamp=self.clock.now(),
            queue_requests=self.state["queue_requests"],
            active_workers=self.state["active_workers"],
            dispatches=self.state["dispatches"]
        )

    def apply_snapshot(self, snapshot: SchedulerStateSnapshot) -> bool:
        """
        Applies a state snapshot on follower node.
        Rejects stale fencing tokens or stale/duplicate versions.
        """
        if snapshot.fencing_token < self.latest_fencing_token:
            return False

        if snapshot.version <= self.current_version:
            return False

        self.current_version = snapshot.version
        self.latest_fencing_token = snapshot.fencing_token
        self.state["queue_requests"] = list(snapshot.queue_requests)
        self.state["active_workers"] = list(snapshot.active_workers)
        self.state["dispatches"] = dict(snapshot.dispatches)
        return True
