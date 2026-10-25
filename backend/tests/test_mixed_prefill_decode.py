import pytest
from scheduler.models import InferenceRequest
from batching.continuous import ContinuousBatcher, SequencePhase

def test_SCH_065_mixed_prefill_and_decode_batching():
    batcher = ContinuousBatcher(max_batch_size=4, max_token_budget_per_step=128)

    # 1. Admit sequence 1 and step once so it enters DECODE phase
    seq_decode = InferenceRequest(request_id="seq-decode", model_name="gpt-2", prompt="hi there", max_tokens=10)
    assert batcher.admit(seq_decode) is True

    # Step 1: seq-decode completes prefill
    r1 = batcher.step()
    assert r1["prefill_count"] == 1
    assert r1["decode_count"] == 0
    assert batcher.active_batch["seq-decode"].phase == SequencePhase.DECODE

    # 2. Admit sequence 2 (new arrival, starts in PREFILL phase)
    seq_prefill = InferenceRequest(request_id="seq-prefill", model_name="gpt-2", prompt="this is a brand new query", max_tokens=10)
    assert batcher.admit(seq_prefill) is True
    assert batcher.active_batch["seq-prefill"].phase == SequencePhase.PREFILL

    # 3. Step 2: Co-schedules both PREFILL and DECODE in the SAME iteration batch!
    r2 = batcher.step()
    assert r2["scheduled_count"] == 2
    assert r2["decode_count"] == 1    # seq-decode stepped
    assert r2["prefill_count"] == 1   # seq-prefill stepped
    assert "seq-decode" in r2["step_tokens"]
    assert "seq-prefill" in r2["step_tokens"]
