import pytest
from coordination.state import DistributedStateManager, SchedulerStateSnapshot
from clock import Clock

def test_SCH_086_distributed_scheduler_state():
    """
    SCH-086: Distributed scheduler state (BE, P0).
    Distributed state sync across multiple scheduler instances (leader/followers)
    with versioned state snapshots and fencing token validation.
    """
    clock = Clock(initial_time=1000.0)
    leader_mgr = DistributedStateManager(node_id="scheduler-leader", clock=clock)
    follower_mgr = DistributedStateManager(node_id="scheduler-follower-1", clock=clock)

    # 1. Leader publishes version 1 snapshot with fencing token 1
    snap1 = leader_mgr.publish_snapshot(
        leader_id="scheduler-leader",
        fencing_token=1,
        queue_requests=[{"request_id": "req-1", "priority": 10}],
        active_workers=[{"worker_id": "w-1", "status": "HEALTHY"}],
        dispatches={"req-1": {"worker_id": "w-1", "status": "IN_FLIGHT"}}
    )
    assert snap1.version == 1
    assert snap1.fencing_token == 1

    # 2. Follower applies snapshot 1 successfully
    applied = follower_mgr.apply_snapshot(snap1)
    assert applied is True
    assert follower_mgr.current_version == 1
    assert follower_mgr.latest_fencing_token == 1
    assert follower_mgr.state["queue_requests"] == [{"request_id": "req-1", "priority": 10}]

    # 3. Duplicate or older version application rejected
    assert follower_mgr.apply_snapshot(snap1) is False

    # 4. New leader elected (fencing token 2) publishes version 2
    clock.advance(5.0)
    snap2 = leader_mgr.publish_snapshot(
        leader_id="scheduler-leader",
        fencing_token=2,
        queue_requests=[],
        active_workers=[{"worker_id": "w-1", "status": "HEALTHY"}],
        dispatches={"req-1": {"worker_id": "w-1", "status": "COMPLETED"}}
    )
    assert snap2.version == 2
    assert follower_mgr.apply_snapshot(snap2) is True
    assert follower_mgr.current_version == 2

    # 5. Stale / deposed leader write carrying old fencing token (1 < 2) is strictly rejected
    with pytest.raises(ValueError, match="Stale fencing token"):
        leader_mgr.publish_snapshot(
            leader_id="deposed-leader",
            fencing_token=1,
            queue_requests=[],
            active_workers=[],
            dispatches={}
        )

    # Follower also rejects any snapshot with stale fencing token
    stale_snap = SchedulerStateSnapshot(
        version=3,
        leader_id="deposed-leader",
        fencing_token=1,
        timestamp=clock.now(),
        queue_requests=[],
        active_workers=[],
        dispatches={}
    )
    assert follower_mgr.apply_snapshot(stale_snap) is False
