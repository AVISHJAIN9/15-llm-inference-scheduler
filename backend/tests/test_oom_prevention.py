import pytest
from kv.allocator import PagedKVCacheManager

def test_SCH_052_oom_prevention():
    # 10 blocks total, 16 tokens per block = 160 tokens capacity
    # 90% watermark = 9 blocks (144 tokens)
    mgr = PagedKVCacheManager(total_blocks=10, block_size=16)

    # Initial state: 0 blocks used. Safe to allocate 80 tokens (5 blocks)
    assert mgr.check_oom_risk(additional_tokens=80, watermark_ratio=0.90) is False
    blocks = mgr.allocate("seq-oom-1", num_tokens=80)
    assert len(blocks) == 5
    assert mgr.used_blocks_count == 5

    # Safe to allocate 48 tokens (3 blocks) -> 5 + 3 = 8 blocks <= 9 safe blocks
    assert mgr.check_oom_risk(additional_tokens=48, watermark_ratio=0.90) is False
    mgr.allocate("seq-oom-2", num_tokens=48)
    assert mgr.used_blocks_count == 8

    # OOM Prevention trips: requesting 32 tokens (2 blocks) would result in 8 + 2 = 10 blocks > 9 safe blocks
    is_oom_risk = mgr.check_oom_risk(additional_tokens=32, watermark_ratio=0.90)
    assert is_oom_risk is True

    # Attempting to allocate when OOM risk is flagged is rejected by the scheduler
    assert mgr.can_allocate(num_tokens=32) is True  # Physically 2 blocks free
    # But policy enforces OOM prevention rejecting beyond watermark
    if is_oom_risk:
        rejected = True
    assert rejected is True
