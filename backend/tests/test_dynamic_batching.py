import pytest
import time
from scheduler.models import InferenceRequest, RequestStatus
from batching.dynamic import DynamicBatcher

def test_SCH_058_dynamic_batching():
    """
    SCH-058: Dynamic batching (BE, P0).
    Dynamically groups arriving requests into batched execution units based on current load,
    adapts batch size up to max_batch_size, and preserves FIFO/priority ordering.
    """
    batcher = DynamicBatcher(max_batch_size=4, min_batch_size=1)

    # 1. Queue is empty -> no batch formed
    assert batcher.has_pending_requests() is False
    assert batcher.form_batch() is None

    # 2. Add single request -> dynamic batcher forms batch of size 1 (adaptive to low traffic)
    req1 = InferenceRequest(request_id="r1", model_name="llama-3-8b", prompt="hello 1", priority=1)
    batcher.enqueue(req1)
    assert batcher.has_pending_requests() is True

    b1 = batcher.form_batch()
    assert b1 is not None
    assert b1.batch_size == 1
    assert b1.requests[0].request_id == "r1"
    assert b1.requests[0].status == RequestStatus.IN_FLIGHT

    # 3. High load: enqueue 6 requests -> batcher forms batch capped at max_batch_size=4
    for i in range(2, 8):
        req = InferenceRequest(request_id=f"r{i}", model_name="llama-3-8b", prompt=f"hello {i}", priority=i)
        batcher.enqueue(req)

    b2 = batcher.form_batch()
    assert b2 is not None
    assert b2.batch_size == 4
    # Highest priority requests should be batched first
    assert [r.request_id for r in b2.requests] == ["r7", "r6", "r5", "r4"]

    # 4. Drain remaining requests
    b3 = batcher.form_batch()
    assert b3 is not None
    assert b3.batch_size == 2
    assert [r.request_id for r in b3.requests] == ["r3", "r2"]

    # Queue empty again
    assert batcher.form_batch() is None
