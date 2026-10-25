import pytest
from kv.allocator import PagedKVCacheManager

def test_SCH_049_paged_kv_cache_address_translation():
    # Block size = 16 tokens
    mgr = PagedKVCacheManager(total_blocks=10, block_size=16)

    # Allocate sequence with 32 tokens -> 2 physical blocks
    blocks = mgr.allocate("seq-paged-1", num_tokens=32)
    assert len(blocks) == 2
    b0, b1 = blocks[0], blocks[1]

    # Virtual token index 0 -> block 0, offset 0
    phys_b, offset = mgr.translate_token_index("seq-paged-1", token_idx=0)
    assert phys_b == b0
    assert offset == 0

    # Virtual token index 15 -> block 0, offset 15
    phys_b, offset = mgr.translate_token_index("seq-paged-1", token_idx=15)
    assert phys_b == b0
    assert offset == 15

    # Virtual token index 16 -> block 1, offset 0
    phys_b, offset = mgr.translate_token_index("seq-paged-1", token_idx=16)
    assert phys_b == b1
    assert offset == 0

    # Virtual token index 31 -> block 1, offset 15
    phys_b, offset = mgr.translate_token_index("seq-paged-1", token_idx=31)
    assert phys_b == b1
    assert offset == 15

    # Virtual token index 32 -> raises IndexError (beyond allocated capacity)
    with pytest.raises(IndexError):
        mgr.translate_token_index("seq-paged-1", token_idx=32)

    # Append slot for token 32
    b2 = mgr.append_slot("seq-paged-1")
    assert b2 is not None
    # Now token 32 is valid and maps to b2, offset 0
    phys_b, offset = mgr.translate_token_index("seq-paged-1", token_idx=32)
    assert phys_b == b2
    assert offset == 0
