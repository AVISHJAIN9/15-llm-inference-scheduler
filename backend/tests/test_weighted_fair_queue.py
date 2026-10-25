import pytest
from scheduler.models import InferenceRequest
from scheduler.queue import WeightedFairQueue

def test_SCH_007_weighted_fair_queue():
    wfq = WeightedFairQueue()
    wfq.set_tenant_weight("tenant_premium", weight=3)
    wfq.set_tenant_weight("tenant_standard", weight=1)

    # Enqueue 30 requests for premium, 30 for standard
    for i in range(30):
        wfq.enqueue(InferenceRequest(request_id=f"prem-{i}", tenant_id="tenant_premium", model_name="gpt-2", prompt="p", max_tokens=10))
        wfq.enqueue(InferenceRequest(request_id=f"std-{i}", tenant_id="tenant_standard", model_name="gpt-2", prompt="p", max_tokens=10))

    assert wfq.size() == 60

    # Pop 40 requests
    dispatched = {"tenant_premium": 0, "tenant_standard": 0}
    for _ in range(40):
        req = wfq.dequeue()
        assert req is not None
        dispatched[req.tenant_id] += 1

    # Ratio should match 3:1 weight distribution -> exactly 30 premium, 10 standard
    assert dispatched["tenant_premium"] == 30
    assert dispatched["tenant_standard"] == 10
