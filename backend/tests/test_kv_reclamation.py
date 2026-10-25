import pytest
from kv.allocator import PagedKVCacheManager

def test_SCH_046_kv_cache_reclamation():
    mgr = PagedKVCacheManager(total_blocks=20, block_size=16)
    initial_free = mgr.free_blocks_count
    assert initial_free == 20

    # Allocate sequence with 48 tokens -> 3 blocks
    blocks = mgr.allocate("seq-reclaim", num_tokens=48)
    assert len(blocks) == 3
    assert mgr.free_blocks_count == 17
    assert mgr.used_blocks_count == 3
    assert mgr.verify_invariants()

    # Reclaim sequence
    ok = mgr.free("seq-reclaim")
    assert ok is True
    assert mgr.get_block_table("seq-reclaim") is None

    # Verify all 3 blocks restored to free list
    assert mgr.free_blocks_count == 20
    assert mgr.used_blocks_count == 0
    assert mgr.verify_invariants()

    # Reclaiming non-existent sequence returns False safely
    assert mgr.free("non-existent") is False
    assert mgr.verify_invariants()
