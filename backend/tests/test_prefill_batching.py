import pytest
from scheduler.models import InferenceRequest, RequestStatus
from kv.allocator import PagedKVCacheManager
from batching.prefill import PrefillBatcher, PrefillBatch

def test_SCH_063_prefill_batching():
    """
    SCH-063: Prefill batching (BE, P0).
    Batches compute-intensive prompt processing phases across multiple requests,
    enforces maximum prefill token budgets, supports chunked prefill for large prompts,
    and transitions completed prefills to decoding state.
    """
    kv_mgr = PagedKVCacheManager(total_blocks=100, block_size=16)
    prefill_batcher = PrefillBatcher(max_prefill_tokens=100, max_sequences=4, kv_manager=kv_mgr)

    # 1. Enqueue 3 requests with various prompt token lengths
    # req1: 30 tokens, req2: 40 tokens, req3: 50 tokens
    req1 = InferenceRequest(request_id="r1", model_name="llama-3-8b", prompt="word " * 30, max_tokens=10)
    req2 = InferenceRequest(request_id="r2", model_name="llama-3-8b", prompt="word " * 40, max_tokens=10)
    req3 = InferenceRequest(request_id="r3", model_name="llama-3-8b", prompt="word " * 50, max_tokens=10)

    prefill_batcher.enqueue(req1)
    prefill_batcher.enqueue(req2)
    prefill_batcher.enqueue(req3)

    # 2. Form prefill batch under budget (100 tokens max):
    # req1 (30 tokens) + req2 (40 tokens) = 70 tokens <= 100.
    # req3 (50 tokens) would reach 120 > 100, so it is deferred to next batch.
    batch1 = prefill_batcher.form_prefill_batch()
    assert batch1 is not None
    assert len(batch1.sequences) == 2
    assert batch1.total_prompt_tokens == 70
    assert [s.request_id for s in batch1.sequences] == ["r1", "r2"]

    # 3. Execute prefill step on batch1
    res1 = prefill_batcher.execute_prefill_batch(batch1)
    assert len(res1.completed_prefills) == 2
    # Verify both transitioned to DECODE phase
    for seq in res1.completed_prefills:
        assert seq.phase == "DECODE"
        assert seq.prefill_processed == seq.prompt_tokens_count

    # 4. Next batch takes req3 (50 tokens <= 100)
    batch2 = prefill_batcher.form_prefill_batch()
    assert batch2 is not None
    assert len(batch2.sequences) == 1
    assert batch2.total_prompt_tokens == 50
    assert batch2.sequences[0].request_id == "r3"

    res2 = prefill_batcher.execute_prefill_batch(batch2)
    assert len(res2.completed_prefills) == 1
    assert res2.completed_prefills[0].phase == "DECODE"

    # Queue empty
    assert prefill_batcher.form_prefill_batch() is None
