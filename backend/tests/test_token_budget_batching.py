import pytest
from scheduler.models import InferenceRequest
from batching.continuous import ContinuousBatcher

def test_SCH_062_token_budget_batching():
    # Token budget per iteration = 10 tokens
    batcher = ContinuousBatcher(max_batch_size=5, max_token_budget_per_step=10)

    # req-a prompt has 6 tokens
    req_a = InferenceRequest(request_id="req-a", model_name="gpt-2", prompt="one two three four five six", max_tokens=10)
    # req-b prompt has 5 tokens
    req_b = InferenceRequest(request_id="req-b", model_name="gpt-2", prompt="alpha beta gamma delta epsilon", max_tokens=10)
    # req-c prompt has 2 tokens
    req_c = InferenceRequest(request_id="req-c", model_name="gpt-2", prompt="short prompt", max_tokens=10)

    assert batcher.admit(req_a) is True
    assert batcher.admit(req_b) is True
    assert batcher.admit(req_c) is True

    # Total tokens needed: 6 + 5 + 2 = 13 > 10 (budget)
    # schedule_iteration must schedule only within the 10 token budget!
    scheduled, budget_used = batcher.schedule_iteration()

    # Budget used must strictly be <= 10
    assert budget_used <= 10
    assert len(scheduled) < 3  # Not all 3 could be scheduled in one step due to budget
    scheduled_ids = [s.request_id for s in scheduled]
    assert "req-a" in scheduled_ids
    assert "req-c" in scheduled_ids
    assert "req-b" not in scheduled_ids  # 6 + 2 = 8 <= 10, but adding 5 would exceed 10
    assert budget_used == 8
