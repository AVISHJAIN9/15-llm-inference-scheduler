import pytest
from clock import Clock
from coordination.workers import WorkerRegistry

def test_SCH_091_worker_heartbeats_and_timeout():
    clk = Clock(initial_time=1000.0)
    registry = WorkerRegistry(clock=clk, heartbeat_timeout=10.0)

    # Register worker-A and worker-B
    registry.register_worker("w-A", "http://w-a:8000", {"gpt-2"})
    registry.register_worker("w-B", "http://w-b:8000", {"gpt-2"})

    assert len(registry.list_healthy_workers()) == 2
    assert len(registry.check_dead_workers()) == 0

    # Advance clock by 5 seconds: both still healthy
    clk.advance(5.0)  # T = 1005.0
    assert len(registry.list_healthy_workers()) == 2

    # w-A sends heartbeat at T = 1005.0
    ok = registry.record_heartbeat("w-A")
    assert ok is True
    assert registry.get_worker("w-A").last_heartbeat == 1005.0

    # Advance clock by 7 seconds (T = 1012.0)
    # w-B has had no heartbeat since 1000.0 (12s ago > 10s timeout) -> w-B is dead!
    # w-A had heartbeat at 1005.0 (7s ago <= 10s timeout) -> w-A is healthy!
    clk.advance(7.0)
    dead = registry.check_dead_workers()
    assert dead == ["w-B"]
    assert registry.get_worker("w-B").is_alive is False

    healthy = registry.list_healthy_workers()
    assert len(healthy) == 1
    assert healthy[0].worker_id == "w-A"
