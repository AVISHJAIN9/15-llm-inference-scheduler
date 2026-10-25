import pytest
from scheduler.models import InferenceRequest
from scheduler.tenant import TenantScheduler, TenantQuotaConfig

def test_SCH_009_tenant_aware_scheduling():
    """
    SCH-009: Tenant-aware scheduling.
    Prevents noisy neighbor starvation, enforces concurrency limits per tenant,
    and fairly interleaves multi-tenant requests.
    """
    scheduler = TenantScheduler()
    scheduler.set_tenant_quota("tenant-a", TenantQuotaConfig(max_concurrency=1, weight=1.0))
    scheduler.set_tenant_quota("tenant-b", TenantQuotaConfig(max_concurrency=2, weight=1.0))

    # Tenant A sends 3 requests
    req_a1 = InferenceRequest(request_id="a1", model_name="m", prompt="p", tenant_id="tenant-a", arrival_time=1.0)
    req_a2 = InferenceRequest(request_id="a2", model_name="m", prompt="p", tenant_id="tenant-a", arrival_time=2.0)
    req_a3 = InferenceRequest(request_id="a3", model_name="m", prompt="p", tenant_id="tenant-a", arrival_time=3.0)

    # Tenant B sends 2 requests
    req_b1 = InferenceRequest(request_id="b1", model_name="m", prompt="p", tenant_id="tenant-b", arrival_time=4.0)
    req_b2 = InferenceRequest(request_id="b2", model_name="m", prompt="p", tenant_id="tenant-b", arrival_time=5.0)

    queue = [req_a1, req_a2, req_a3, req_b1, req_b2]

    # First dispatch: both A and B are under limit. A1 arrived earlier, so A1 is dispatched.
    selected_1 = scheduler.select_next(queue)
    assert selected_1 is not None
    assert selected_1.request_id == "a1"
    scheduler.on_request_dispatched(selected_1)
    queue.remove(selected_1)

    # Now Tenant A has 1 active request (= max_concurrency 1).
    # Next dispatch: Tenant A is throttled! Tenant B (B1) MUST be picked even though A2 and A3 arrived earlier!
    selected_2 = scheduler.select_next(queue)
    assert selected_2 is not None
    assert selected_2.request_id == "b1"
    scheduler.on_request_dispatched(selected_2)
    queue.remove(selected_2)

    # Tenant B has 1 active request (< max_concurrency 2). Next is B2.
    selected_3 = scheduler.select_next(queue)
    assert selected_3 is not None
    assert selected_3.request_id == "b2"
    scheduler.on_request_dispatched(selected_3)
    queue.remove(selected_3)

    # Now both A and B are at max concurrency (A: 1/1, B: 2/2).
    # No request can be dispatched right now!
    assert scheduler.select_next(queue) is None

    # When A1 completes:
    scheduler.on_request_completed("tenant-a")
    # Now A has an open slot: A2 can now be dispatched!
    selected_4 = scheduler.select_next(queue)
    assert selected_4 is not None
    assert selected_4.request_id == "a2"

    # Validation
    with pytest.raises(ValueError):
        TenantQuotaConfig(max_concurrency=-1)
