import pytest
from scheduler.models import InferenceRequest
from batching.continuous import ContinuousBatcher

def test_SCH_061_max_batch_size_enforcement():
    batcher = ContinuousBatcher(max_batch_size=3)
    assert batcher.max_batch_size == 3
    assert batcher.current_batch_size == 0

    reqs = [
        InferenceRequest(request_id=f"req-bs-{i}", model_name="gpt-2", prompt=f"prompt {i}", max_tokens=10)
        for i in range(3)
    ]

    # Admit up to max_batch_size (3)
    for r in reqs:
        assert batcher.admit(r) is True

    assert batcher.current_batch_size == 3
    assert batcher.can_admit(reqs[0]) is False

    # Attempt to admit 4th request -> strictly rejected / stays queued
    overflow_req = InferenceRequest(request_id="req-bs-overflow", model_name="gpt-2", prompt="overflow", max_tokens=10)
    assert batcher.can_admit(overflow_req) is False
    assert batcher.admit(overflow_req) is False
    assert batcher.current_batch_size == 3
