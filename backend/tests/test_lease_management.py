import pytest
from clock import Clock
from coordination.election import LeaderElector

def test_SCH_089_lease_management_and_fencing_validation():
    clk = Clock(initial_time=200.0)
    elector = LeaderElector(clock=clk, default_lease_ttl=10.0)

    # Leader A acquires lease with token 1
    ok_a, token_a = elector.acquire_or_renew("leader-A")
    assert ok_a is True
    assert token_a == 1
    assert elector.validate_write(fencing_token=1) is True

    # Leader A renews lease at T=205 (before expiry at 210)
    clk.advance(5.0)
    ok_renew, token_renew = elector.acquire_or_renew("leader-A")
    assert ok_renew is True
    assert token_renew == 1  # Fencing token remains 1 on renewal
    assert elector.lease_expires_at == 215.0  # Extended to 205 + 10 = 215

    # Simulate network partition or pause on Leader A: clock advances to 220
    clk.advance(15.0)
    assert not elector.is_leader("leader-A")

    # Leader B takes over -> fencing token increments to 2
    ok_b, token_b = elector.acquire_or_renew("leader-B")
    assert ok_b is True
    assert token_b == 2
    assert elector.validate_write(fencing_token=2) is True

    # Now Leader A recovers and attempts a late write using its stale fencing token 1
    # Strict fencing rule: late write MUST be rejected!
    assert elector.validate_write(fencing_token=1) is False
