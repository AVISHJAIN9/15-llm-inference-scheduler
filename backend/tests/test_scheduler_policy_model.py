import pytest
from scheduler.models import InferenceRequest
from scheduler.policy import PolicyType, SchedulerPolicyConfig, SchedulerPolicyModel

def test_SCH_001_scheduler_policy_model():
    """
    SCH-001: Scheduler policy model.
    Validates policy configuration, validation, ranking evaluation, and dynamic switching.
    """
    # 1. Configuration validation
    config = SchedulerPolicyConfig(
        policy_type=PolicyType.FIFO,
        aging_factor=0.5,
        deadline_slack_seconds=2.0
    )
    assert config.policy_type == PolicyType.FIFO
    assert config.aging_factor == 0.5

    model = SchedulerPolicyModel(config)
    assert model.current_policy == PolicyType.FIFO

    # Candidate requests
    req1 = InferenceRequest(
        request_id="req-1",
        model_name="llama-3",
        prompt="hello",
        arrival_time=10.0,
        priority=1,
        weight=1.0,
        deadline=30.0
    )
    req2 = InferenceRequest(
        request_id="req-2",
        model_name="llama-3",
        prompt="world",
        arrival_time=5.0,
        priority=10,
        weight=2.0,
        deadline=15.0
    )
    req3 = InferenceRequest(
        request_id="req-3",
        model_name="llama-3",
        prompt="system",
        arrival_time=8.0,
        priority=5,
        weight=4.0,
        deadline=20.0
    )

    candidates = [req1, req2, req3]

    # Under FIFO, ordered by arrival time: req2 (5.0), req3 (8.0), req1 (10.0)
    ordered_fifo = model.rank_candidates(candidates, current_time=12.0)
    assert [r.request_id for r in ordered_fifo] == ["req-2", "req-3", "req-1"]

    # Switch to PRIORITY policy: higher effective priority first
    # At current_time=12.0:
    # req1: base 1 + 0.5*(12-10) = 2.0
    # req2: base 10 + 0.5*(12-5) = 13.5
    # req3: base 5 + 0.5*(12-8) = 7.0
    model.set_policy(PolicyType.PRIORITY, aging_factor=0.5)
    ordered_priority = model.rank_candidates(candidates, current_time=12.0)
    assert [r.request_id for r in ordered_priority] == ["req-2", "req-3", "req-1"]

    # Switch to DEADLINE_AWARE: earliest deadline first
    model.set_policy(PolicyType.DEADLINE_AWARE)
    ordered_deadline = model.rank_candidates(candidates, current_time=12.0)
    assert [r.request_id for r in ordered_deadline] == ["req-2", "req-3", "req-1"]

    # Test invalid config raises ValueError
    with pytest.raises(ValueError):
        SchedulerPolicyConfig(policy_type=PolicyType.FIFO, aging_factor=-1.0)
