import pytest
from kv.allocator import PagedKVCacheManager

def test_SCH_053_kv_cache_eviction_policy():
    # 10 blocks total: plenty of capacity
    mgr = PagedKVCacheManager(total_blocks=10, block_size=16)

    # Allocate active sequence seq-active first (refcount = 1)
    b_active = mgr.allocate("seq-active", num_tokens=16)
    active_block_id = b_active[0]
    assert mgr.blocks[active_block_id].ref_count == 1

    # Allocate and register 2 prefix blocks: p1 and p2
    b1 = mgr.allocate("seq-p1", num_tokens=16)
    h1 = mgr.register_prefix("prefix-alpha", b1[0])
    b2 = mgr.allocate("seq-p2", num_tokens=16)
    h2 = mgr.register_prefix("prefix-beta", b2[0])

    # Release seq-p1 and seq-p2 so their refcounts drop to 0
    mgr.free("seq-p1")
    mgr.free("seq-p2")
    assert mgr.blocks[b1[0]].ref_count == 0
    assert mgr.blocks[b2[0]].ref_count == 0
    assert mgr.blocks[active_block_id].ref_count == 1

    # Eviction rule: NEVER evict active block with ref_count > 0!
    # Evict 1 LRU block: should evict prefix-alpha (oldest 0-refcount block)
    evicted_count1 = mgr.evict_lru_prefix_blocks(target_blocks=1)
    assert evicted_count1 == 1
    assert h1 not in mgr.prefix_cache
    assert h2 in mgr.prefix_cache
    assert mgr.blocks[active_block_id].ref_count == 1  # Untouched active block

    # Evict next block: should evict prefix-beta
    evicted_count2 = mgr.evict_lru_prefix_blocks(target_blocks=1)
    assert evicted_count2 == 1
    assert h2 not in mgr.prefix_cache

    # Attempt to evict more: no 0-refcount candidates left -> 0 evicted
    evicted_none = mgr.evict_lru_prefix_blocks(target_blocks=1)
    assert evicted_none == 0
    assert mgr.blocks[active_block_id].ref_count == 1
    assert mgr.verify_invariants()
