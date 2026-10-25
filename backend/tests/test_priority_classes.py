import pytest
from scheduler.models import InferenceRequest
from scheduler.priority_classes import PriorityClass, PriorityClassConfig, PriorityClassRegistry

def test_SCH_004_priority_classes():
    """
    SCH-004: Priority classes.
    Validates priority class tiers, base weights, preemption flags, and anti-starvation calculation.
    """
    registry = PriorityClassRegistry()
    # Check default classes are registered
    assert PriorityClass.CRITICAL in registry.classes
    assert PriorityClass.INTERACTIVE in registry.classes
    assert PriorityClass.BATCH in registry.classes
    assert PriorityClass.BACKGROUND in registry.classes

    crit = registry.get_class(PriorityClass.CRITICAL)
    assert crit.base_priority >= 100
    assert crit.can_preempt is True

    bg = registry.get_class(PriorityClass.BACKGROUND)
    assert bg.base_priority < crit.base_priority

    # Calculate effective priority with class-based aging
    req_crit = InferenceRequest(
        request_id="req-crit",
        model_name="llama-3",
        prompt="system alert",
        arrival_time=10.0,
        metadata={"priority_class": "CRITICAL"}
    )
    req_bg = InferenceRequest(
        request_id="req-bg",
        model_name="llama-3",
        prompt="offline indexing",
        arrival_time=0.0,
        metadata={"priority_class": "BACKGROUND"}
    )

    # At current_time=10.0, CRITICAL just arrived (100 + 0*rate) > BACKGROUND (1 + 10*0.5)
    score_crit = registry.compute_effective_priority(req_crit, current_time=10.0)
    score_bg = registry.compute_effective_priority(req_bg, current_time=10.0)
    assert score_crit > score_bg

    # Order candidates by priority class
    candidates = [req_bg, req_crit]
    ordered = registry.rank_by_class(candidates, current_time=10.0)
    assert [r.request_id for r in ordered] == ["req-crit", "req-bg"]

    # Starvation boost: after a very long wait (e.g. 500s), background boosts past newly arrived critical
    score_bg_boosted = registry.compute_effective_priority(req_bg, current_time=500.0)
    assert score_bg_boosted > score_crit

    # Custom class registration validation
    with pytest.raises(ValueError):
        PriorityClassConfig(name="INVALID", base_priority=-5)
