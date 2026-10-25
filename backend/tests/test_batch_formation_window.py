import pytest
from scheduler.models import InferenceRequest, RequestStatus
from batching.dynamic import DynamicBatcher
from clock import Clock


def test_SCH_060_batch_formation_window():
    """
    SCH-060: Batch formation window (BE, P0).
    Holds request batch formation open up to max_wait_ms to maximize batch density,
    forming immediately if max_batch_size is reached, or firing upon window expiration.
    Deterministic clock verification.
    """
    clock = Clock(initial_time=1000.0)
    batcher = DynamicBatcher(
        max_batch_size=4,
        min_batch_size=1,
        max_wait_ms=50.0,  # 50ms window
        clock=clock
    )

    # 1. First request arrives at t=1000.0 (queue size 1 < max_batch_size 4)
    req1 = InferenceRequest(request_id="req-1", model_name="llama-3-8b", prompt="hi 1", arrival_time=1000.0)
    batcher.enqueue(req1)

    # 2. At t=1000.020 (20ms elapsed < 50ms window): batch must NOT form yet
    clock.advance(0.020)
    assert batcher.form_batch() is None
    assert batcher.has_pending_requests() is True

    # 3. Second request arrives at t=1000.030 (queue size 2 < 4)
    req2 = InferenceRequest(request_id="req-2", model_name="llama-3-8b", prompt="hi 2", arrival_time=1000.030)
    batcher.enqueue(req2)
    clock.advance(0.010)  # total 30ms elapsed since earliest request
    assert batcher.form_batch() is None

    # 4. Advance clock by 0.025s -> total 55ms elapsed (> 50ms max_wait_ms window)
    clock.advance(0.025)
    batch = batcher.form_batch()
    assert batch is not None
    assert batch.batch_size == 2
    assert [r.request_id for r in batch.requests] == ["req-1", "req-2"]
    assert batch.requests[0].status == RequestStatus.IN_FLIGHT

    # 5. Full capacity bypass: enqueue 4 requests at once -> forms immediately regardless of window
    for i in range(3, 7):
        batcher.enqueue(InferenceRequest(request_id=f"req-{i}", model_name="llama-3-8b", prompt=f"hi {i}", arrival_time=clock.now()))

    instant_batch = batcher.form_batch()
    assert instant_batch is not None
    assert instant_batch.batch_size == 4
    assert [r.request_id for r in instant_batch.requests] == ["req-3", "req-4", "req-5", "req-6"]
