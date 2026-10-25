import pytest
from scheduler.models import InferenceRequest, RequestStatus
from kv.allocator import PagedKVCacheManager
from batching.decode import DecodeBatcher

def test_SCH_064_decode_batching():
    """
    SCH-064: Decode batching (BE, P0).
    Synchronously batches autoregressive token generation across all active sequences,
    advances KV cache slots per step, detects sequence completion, and reclaims memory.
    """
    kv_mgr = PagedKVCacheManager(total_blocks=50, block_size=16)
    decode_batcher = DecodeBatcher(max_decode_batch_size=4, kv_manager=kv_mgr)

    # 1. Add 3 active decoding requests
    # req1 needs 2 tokens, req2 needs 3 tokens, req3 needs 1 token
    req1 = InferenceRequest(request_id="r1", model_name="llama-3-8b", prompt="hello", max_tokens=2)
    req2 = InferenceRequest(request_id="r2", model_name="llama-3-8b", prompt="hi", max_tokens=3)
    req3 = InferenceRequest(request_id="r3", model_name="llama-3-8b", prompt="hey", max_tokens=1)

    # Allocate initial KV blocks
    for r in [req1, req2, req3]:
        kv_mgr.allocate(r.request_id, num_tokens=16)
        decode_batcher.add_decoding_sequence(r)

    assert decode_batcher.active_count == 3

    # 2. Step 1: all 3 sequences generate 1 token
    # req3 has max_tokens=1 -> should finish on Step 1!
    step1 = decode_batcher.step()
    assert step1.step_number == 1
    assert len(step1.tokens_generated) == 3
    assert "r1" in step1.tokens_generated
    assert "r2" in step1.tokens_generated
    assert "r3" in step1.tokens_generated
    assert step1.finished_request_ids == ["r3"]
    assert req3.status == RequestStatus.COMPLETED
    assert decode_batcher.active_count == 2
    # Verify req3 KV blocks were reclaimed
    assert "r3" not in kv_mgr.block_tables

    # 3. Step 2: r1 and r2 generate token
    # req1 has max_tokens=2 -> should finish on Step 2!
    step2 = decode_batcher.step()
    assert step2.step_number == 2
    assert len(step2.tokens_generated) == 2
    assert step2.finished_request_ids == ["r1"]
    assert req1.status == RequestStatus.COMPLETED
    assert decode_batcher.active_count == 1

    # 4. Step 3: r2 generates final token
    # req2 has max_tokens=3 -> should finish on Step 3!
    step3 = decode_batcher.step()
    assert step3.step_number == 3
    assert step3.finished_request_ids == ["r2"]
    assert req2.status == RequestStatus.COMPLETED
    assert decode_batcher.active_count == 0

    # 5. Further steps with empty batch return empty result
    step4 = decode_batcher.step()
    assert len(step4.tokens_generated) == 0
    assert len(step4.finished_request_ids) == 0
