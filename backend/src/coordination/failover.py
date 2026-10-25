"""
Scheduler failover coordinator (SCH-094).
Monitors leader scheduler health, triggers automated standby takeover upon leader failure,
and enforces monotonically increasing fencing tokens to prevent split-brain execution.
"""

from typing import Dict, List, Optional, Tuple, Any
from pydantic import BaseModel
from clock import Clock
from coordination.election import LeaderElector


class SchedulerNode(BaseModel):
    scheduler_id: str
    endpoint_url: str
    priority: int = 0
    is_leader: bool = False
    fencing_token: int = 0
    last_heartbeat: float = 0.0


class SchedulerFailoverCoordinator:
    """
    Automated scheduler failover coordinator (SCH-094).
    """
    def __init__(
        self,
        clock: Optional[Clock] = None,
        lease_ttl: float = 5.0,
        heartbeat_timeout: float = 4.0
    ):
        self.clock = clock or Clock()
        self.lease_ttl = lease_ttl
        self.heartbeat_timeout = heartbeat_timeout
        self.elector = LeaderElector(clock=self.clock, default_lease_ttl=lease_ttl)
        self.nodes: Dict[str, SchedulerNode] = {}
        self.failover_events: List[Dict[str, Any]] = []

    def register_node(self, scheduler_id: str, endpoint_url: str, priority: int = 0) -> SchedulerNode:
        node = SchedulerNode(
            scheduler_id=scheduler_id,
            endpoint_url=endpoint_url,
            priority=priority,
            last_heartbeat=self.clock.now()
        )
        self.nodes[scheduler_id] = node
        return node

    def heartbeat(self, scheduler_id: str) -> bool:
        """Records a heartbeat from a scheduler node."""
        node = self.nodes.get(scheduler_id)
        if not node:
            return False
        now = self.clock.now()
        node.last_heartbeat = now
        if node.is_leader:
            ok, token = self.elector.acquire_or_renew(scheduler_id, self.lease_ttl)
            node.fencing_token = token
            return ok
        return True

    def elect_initial_leader(self) -> Optional[str]:
        """Elects initial leader among registered nodes sorted by priority descending."""
        if not self.nodes:
            return None
        sorted_nodes = sorted(self.nodes.values(), key=lambda n: (-n.priority, n.scheduler_id))
        candidate = sorted_nodes[0]
        ok, token = self.elector.acquire_or_renew(candidate.scheduler_id, self.lease_ttl)
        if ok:
            candidate.is_leader = True
            candidate.fencing_token = token
            return candidate.scheduler_id
        return None

    def check_and_failover(self) -> Optional[Tuple[str, str, int]]:
        """
        Checks current leader health. If leader missed heartbeats or lease expired,
        triggers failover to highest-priority healthy standby node.
        Returns (old_leader_id, new_leader_id, new_fencing_token) or None.
        """
        now = self.clock.now()
        current_leader_id = self.elector.current_leader_id
        if not current_leader_id:
            return None

        leader_node = self.nodes.get(current_leader_id)
        leader_healthy = (
            leader_node is not None
            and (now - leader_node.last_heartbeat) <= self.heartbeat_timeout
            and self.elector.is_leader(current_leader_id)
        )

        if leader_healthy:
            return None  # Leader healthy, no failover needed

        # Leader failed: select best standby candidate
        standbys = [
            n for n in self.nodes.values()
            if n.scheduler_id != current_leader_id
            and (now - n.last_heartbeat) <= self.heartbeat_timeout
        ]
        if not standbys:
            return None  # No healthy standby available



        standbys.sort(key=lambda n: (-n.priority, n.scheduler_id))
        successor = standbys[0]

        # Acquire leadership for successor (guarantees fencing token increments)
        ok, new_token = self.elector.acquire_or_renew(successor.scheduler_id, self.lease_ttl)
        if not ok:
            return None

        old_leader = current_leader_id
        if leader_node:
            leader_node.is_leader = False

        successor.is_leader = True
        successor.fencing_token = new_token

        event = {
            "from_leader": old_leader,
            "to_leader": successor.scheduler_id,
            "fencing_token": new_token,
            "timestamp": now
        }
        self.failover_events.append(event)
        return old_leader, successor.scheduler_id, new_token

    def validate_scheduling_write(self, scheduler_id: str, fencing_token: int) -> bool:
        """
        Enforces strict fencing token validation.
        Deposed leader writes carrying stale tokens are rejected.
        """
        node = self.nodes.get(scheduler_id)
        if not node or not node.is_leader:
            return False
        return self.elector.validate_write(fencing_token)
