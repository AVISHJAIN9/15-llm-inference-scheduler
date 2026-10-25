import pytest
from coordination.shared_queue import SharedQueueCoordinator
from scheduler.models import InferenceRequest
from clock import Clock

def test_SCH_087_shared_queue_coordination():
    """
    SCH-087: Shared queue coordination (BE, P0).
    Distributed queue coordination with lease-based claim, renew, ack, nack,
    and automatic lease expiration recovery.
    """
    clock = Clock(initial_time=100.0)
    coord = SharedQueueCoordinator(clock=clock)

    r1 = InferenceRequest(request_id="r1", model_name="m1", prompt="p1", priority=10, arrival_time=100.0)
    r2 = InferenceRequest(request_id="r2", model_name="m1", prompt="p2", priority=5, arrival_time=101.0)
    coord.enqueue(r1)
    coord.enqueue(r2)

    assert coord.pending_count() == 2

    # 1. Scheduler A claims top request (r1, priority 10) with 5-second lease
    claim_a = coord.claim_request(scheduler_id="sched-A", lease_ttl=5.0)
    assert claim_a is not None
    req_claimed, lease_id_a = claim_a
    assert req_claimed.request_id == "r1"
    assert coord.pending_count() == 1

    # Scheduler B tries to claim simultaneously: gets r2 (r1 is safely leased, no double claim)
    claim_b = coord.claim_request(scheduler_id="sched-B", lease_ttl=5.0)
    assert claim_b is not None
    req_b, lease_id_b = claim_b
    assert req_b.request_id == "r2"
    assert coord.pending_count() == 0

    # 2. Scheduler B successfully finishes work and sends ack -> r2 completed and removed
    assert coord.ack(lease_id_b) is True
    assert coord.is_completed("r2") is True

    # 3. Scheduler A crashes or hangs! Clock advances past lease TTL (5 seconds)
    clock.advance(6.0)  # Clock is now 106.0 > 105.0 lease expiry

    # Sched-A tries to ack after lease expiration -> rejected!
    assert coord.ack(lease_id_a) is False

    # Coordinator reclaims expired leases -> r1 returned to queue
    reclaimed = coord.reclaim_expired_leases()
    assert reclaimed == 1
    assert coord.pending_count() == 1

    # 4. Scheduler C claims the reclaimed r1
    claim_c = coord.claim_request(scheduler_id="sched-C", lease_ttl=5.0)
    assert claim_c is not None
    req_c, lease_id_c = claim_c
    assert req_c.request_id == "r1"

    # Sched-C sends nack with requeue=False (e.g. invalid request or fatal error)
    assert coord.nack(lease_id_c, requeue=False) is True
    assert coord.pending_count() == 0
