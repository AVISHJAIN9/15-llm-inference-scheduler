import pytest
from scheduler.models import InferenceRequest, RequestStatus
from batching.continuous import ContinuousBatcher

def test_SCH_057_continuous_batching_join_and_leave():
    batcher = ContinuousBatcher(max_batch_size=2)
    assert batcher.current_batch_size == 0

    req1 = InferenceRequest(request_id="req-short", model_name="gpt-2", prompt="hi", max_tokens=2)
    req2 = InferenceRequest(request_id="req-long", model_name="gpt-2", prompt="hello world", max_tokens=4)

    # Admit both
    assert batcher.admit(req1) is True
    assert batcher.admit(req2) is True
    assert batcher.current_batch_size == 2

    # Step 1: Both generate 1 token
    res1 = batcher.step()
    assert res1["active_count"] == 2
    assert res1["finished_count"] == 0
    assert "req-short" in res1["step_tokens"]
    assert "req-long" in res1["step_tokens"]

    # Step 2: req-short completes at 2 tokens and leaves the batch!
    res2 = batcher.step()
    assert res2["finished_count"] == 1
    assert req1.status == RequestStatus.COMPLETED
    assert batcher.current_batch_size == 1  # Only req-long active

    # New request joins continuous batch between decode steps without waiting for req-long!
    req3 = InferenceRequest(request_id="req-new", model_name="gpt-2", prompt="new prompt", max_tokens=2)
    assert batcher.admit(req3) is True
    assert batcher.current_batch_size == 2

    # Step 3: req-long (step 3) and req-new (step 1) step together
    res3 = batcher.step()
    assert "req-long" in res3["step_tokens"]
    assert "req-new" in res3["step_tokens"]
