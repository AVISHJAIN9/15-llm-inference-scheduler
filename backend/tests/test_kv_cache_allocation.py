import pytest
from kv.allocator import PagedKVCacheManager

def test_SCH_045_kv_cache_allocation():
    # 10 blocks total, 16 tokens per block
    mgr = PagedKVCacheManager(total_blocks=10, block_size=16)

    # Allocate sequence requiring 48 tokens -> ceil(48 / 16) = 3 blocks (full)
    b_seq = mgr.allocate("seq-alloc-1", num_tokens=48)
    assert b_seq is not None
    assert len(b_seq) == 3
    assert mgr.get_block_table("seq-alloc-1") == b_seq

    # Verify block ref counts
    for b_id in b_seq:
        assert mgr.blocks[b_id].ref_count == 1

    assert mgr.used_blocks_count == 3
    assert mgr.free_blocks_count == 7

    # Append slot during token generation
    extra_block = mgr.append_slot("seq-alloc-1")
    assert extra_block is not None
    assert len(mgr.get_block_table("seq-alloc-1")) == 4
    assert mgr.used_blocks_count == 4
    assert mgr.free_blocks_count == 6

    # Attempt to allocate more than remaining free capacity (6 blocks * 16 = 96 tokens; request 120 -> 8 blocks)
    overflow = mgr.allocate("seq-overflow", num_tokens=120)
    assert overflow is None  # Safe rejection, no OOM over-allocation
