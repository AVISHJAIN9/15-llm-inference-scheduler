import pytest
from clock import Clock
from coordination.election import LeaderElector

def test_SCH_085_leader_election():
    clk = Clock(initial_time=100.0)
    elector = LeaderElector(clock=clk, default_lease_ttl=5.0)

    # Initially no leader
    assert not elector.is_leader("node-1")
    assert elector.fencing_token == 0

    # node-1 acquires leadership -> succeeds, fencing token becomes 1
    ok1, token1 = elector.acquire_or_renew("node-1")
    assert ok1 is True
    assert token1 == 1
    assert elector.is_leader("node-1")
    assert not elector.is_leader("node-2")

    # node-2 attempts to take over while node-1's lease is valid -> rejected!
    ok2, token2 = elector.acquire_or_renew("node-2")
    assert ok2 is False
    assert token2 == 1
    assert elector.is_leader("node-1")

    # Advance clock past lease expiry (5 seconds -> advance 6 seconds to 106.0)
    clk.advance(6.0)
    assert not elector.is_leader("node-1")  # Lease expired

    # node-2 now acquires leadership -> succeeds, fencing token increments to 2
    ok3, token3 = elector.acquire_or_renew("node-2")
    assert ok3 is True
    assert token3 == 2
    assert elector.is_leader("node-2")
