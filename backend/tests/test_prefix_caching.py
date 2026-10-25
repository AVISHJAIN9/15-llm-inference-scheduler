import pytest
from kv.allocator import PagedKVCacheManager

def test_SCH_048_prefix_caching():
    mgr = PagedKVCacheManager(total_blocks=20, block_size=16)

    prompt_prefix = "System: You are an expert coding assistant."
    # Initial sequence seq-1 allocates 16 tokens and registers the prefix
    blocks1 = mgr.allocate("seq-1", num_tokens=16)
    assert len(blocks1) == 1
    p_block_id = blocks1[0]
    mgr.register_prefix(prompt_prefix, p_block_id)

    assert mgr.used_blocks_count == 1
    assert mgr.free_blocks_count == 19

    # Now seq-2 arrives with the same system prompt prefix and 32 total tokens
    # Instead of allocating 2 fresh blocks, it reuses p_block_id (refcount increments to 2)
    # and only allocates 1 fresh block!
    blocks2 = mgr.allocate_with_prefix("seq-2", prefix_tokens=prompt_prefix, total_tokens=32)
    assert blocks2 is not None
    assert len(blocks2) == 2
    assert blocks2[0] == p_block_id  # Shared prefix block
    assert mgr.blocks[p_block_id].ref_count == 2
    # Total used blocks across both sequences is 2, not 3!
    assert mgr.used_blocks_count == 2
    assert mgr.free_blocks_count == 18

    # Free seq-1: refcount on p_block_id drops to 1, block is NOT returned to free list yet
    mgr.free("seq-1")
    assert mgr.blocks[p_block_id].ref_count == 1
    assert mgr.used_blocks_count == 2  # seq-2 still holding it

    # Free seq-2: refcount drops to 0, both blocks returned to free list
    mgr.free("seq-2")
    assert mgr.blocks[p_block_id].ref_count == 0
    assert mgr.free_blocks_count == 20
    assert mgr.used_blocks_count == 0
    assert mgr.verify_invariants()
