import pytest
from kv.allocator import PagedKVCacheManager

def test_SCH_043_kv_cache_manager_invariants():
    # Manager initialized with 50 blocks, 16 tokens/block
    mgr = PagedKVCacheManager(total_blocks=50, block_size=16)

    assert mgr.total_blocks == 50
    assert mgr.free_blocks_count == 50
    assert mgr.used_blocks_count == 0
    assert mgr.verify_invariants()

    # Pre-allocation check
    assert mgr.can_allocate(num_tokens=32) is True
    # 51 blocks * 16 tokens = 816 tokens -> exceeds 50 blocks
    assert mgr.can_allocate(num_tokens=816) is False

    # Allocate 32 tokens -> 2 blocks
    blocks = mgr.allocate("seq-1", num_tokens=32)
    assert len(blocks) == 2
    assert mgr.free_blocks_count == 48
    assert mgr.used_blocks_count == 2
    assert mgr.verify_invariants()
    assert mgr.free_blocks_count + mgr.used_blocks_count == 50
