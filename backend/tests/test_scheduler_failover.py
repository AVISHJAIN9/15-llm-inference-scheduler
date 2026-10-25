import pytest
from coordination.failover import SchedulerFailoverCoordinator
from clock import Clock

def test_SCH_094_scheduler_failover():
    """
    SCH-094: Scheduler failover (BE, P0).
    Kill the leader under load: heartbeat timeout detection,
    automated standby takeover by highest-priority node,
    fencing token promotion, and strict rejection of deposed leader writes (S15-04).
    """
    clock = Clock(initial_time=1000.0)
    coord = SchedulerFailoverCoordinator(
        clock=clock,
        lease_ttl=5.0,
        heartbeat_timeout=4.0
    )

    # 1. Register 3 scheduler nodes: leader candidate (priority 10), standby-1 (priority 20 - highest), standby-2 (priority 5)
    n1 = coord.register_node(scheduler_id="sched-1", endpoint_url="http://sched-1:8000", priority=10)
    n2 = coord.register_node(scheduler_id="sched-2", endpoint_url="http://sched-2:8000", priority=20)
    n3 = coord.register_node(scheduler_id="sched-3", endpoint_url="http://sched-3:8000", priority=5)

    # Elect initial leader -> sched-2 (highest priority 20)
    initial_leader = coord.elect_initial_leader()
    assert initial_leader == "sched-2"
    assert n2.is_leader is True
    assert n2.fencing_token == 1

    # Valid write from active leader with token 1 is accepted
    assert coord.validate_scheduling_write("sched-2", fencing_token=1) is True

    # 2. Sched-2 crashes and misses heartbeats. Sched-1 and Sched-3 continue heartbeating
    clock.advance(5.0)  # Clock is now 1005.0 (> 4.0 heartbeat timeout and >= 5.0 lease expiry)
    coord.heartbeat("sched-1")
    coord.heartbeat("sched-3")

    # 3. Failover check triggers takeover by highest priority healthy standby (sched-1, priority 10 > sched-3 priority 5)
    failover = coord.check_and_failover()
    assert failover is not None
    old_l, new_l, new_token = failover
    assert old_l == "sched-2"
    assert new_l == "sched-1"
    assert new_token == 2
    assert n1.is_leader is True
    assert n2.is_leader is False

    # 4. Strict fencing token validation: deposed leader (sched-2) attempts late write with old token 1 -> REJECTED
    assert coord.validate_scheduling_write("sched-2", fencing_token=1) is False

    # New leader write with token 2 -> ACCEPTED
    assert coord.validate_scheduling_write("sched-1", fencing_token=2) is True

    # 5. Failover events audit trail recorded
    assert len(coord.failover_events) == 1
    ev = coord.failover_events[0]
    assert ev["from_leader"] == "sched-2"
    assert ev["to_leader"] == "sched-1"
    assert ev["fencing_token"] == 2
