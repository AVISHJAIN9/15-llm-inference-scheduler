import pytest
from scheduler.models import InferenceRequest
from scheduler.deadline import DeadlineScheduler, InfeasibleDeadlineAction

def test_SCH_008_deadline_aware_scheduling():
    """
    SCH-008: Deadline-aware scheduling.
    Picks the earliest FEASIBLE deadline; infeasible deadlines are deprioritized or rejected.
    """
    scheduler = DeadlineScheduler(
        tokens_per_sec=20.0,
        time_to_first_token=0.1,
        infeasible_action=InfeasibleDeadlineAction.DEPRIORITIZE
    )

    current_time = 100.0

    # Req 1: max_tokens=100 -> takes 0.1 + 100/20 = 5.1s.
    # Estimated finish = 105.1s. Deadline = 110.0s -> FEASIBLE (Slack = 4.9s)
    req1 = InferenceRequest(
        request_id="req-feasible-later",
        model_name="llama-3",
        prompt="p1",
        max_tokens=100,
        arrival_time=current_time,
        deadline=110.0
    )

    # Req 2: max_tokens=50 -> takes 0.1 + 50/20 = 2.6s.
    # Estimated finish = 102.6s. Deadline = 105.0s -> FEASIBLE (Slack = 2.4s)
    # Earlier deadline than req1!
    req2 = InferenceRequest(
        request_id="req-feasible-earliest",
        model_name="llama-3",
        prompt="p2",
        max_tokens=50,
        arrival_time=current_time,
        deadline=105.0
    )

    # Req 3: max_tokens=200 -> takes 0.1 + 200/20 = 10.1s.
    # Estimated finish = 110.1s. Deadline = 102.0s -> INFEASIBLE (already cannot meet deadline)
    req3 = InferenceRequest(
        request_id="req-infeasible",
        model_name="llama-3",
        prompt="p3",
        max_tokens=200,
        arrival_time=current_time,
        deadline=102.0
    )

    # Req 4: No deadline -> fallback to arrival_time
    req4 = InferenceRequest(
        request_id="req-no-deadline",
        model_name="llama-3",
        prompt="p4",
        max_tokens=20,
        arrival_time=current_time + 1.0,
        deadline=None
    )

    candidates = [req1, req3, req4, req2]

    # Verify feasibility checks
    assert scheduler.is_feasible(req1, current_time) is True
    assert scheduler.is_feasible(req2, current_time) is True
    assert scheduler.is_feasible(req3, current_time) is False
    assert scheduler.is_feasible(req4, current_time) is True

    # Under Earliest Feasible Deadline First:
    # 1. req-feasible-earliest (deadline 105.0)
    # 2. req-feasible-later (deadline 110.0)
    # 3. req-no-deadline (no deadline)
    # 4. req-infeasible (deprioritized because it cannot meet deadline)
    ranked = scheduler.rank_candidates(candidates, current_time=current_time)
    assert [r.request_id for r in ranked] == [
        "req-feasible-earliest",
        "req-feasible-later",
        "req-no-deadline",
        "req-infeasible"
    ]

    # Test reject action
    scheduler_reject = DeadlineScheduler(
        tokens_per_sec=20.0,
        time_to_first_token=0.1,
        infeasible_action=InfeasibleDeadlineAction.REJECT
    )
    ranked_reject = scheduler_reject.rank_candidates(candidates, current_time=current_time)
    assert "req-infeasible" not in [r.request_id for r in ranked_reject]
