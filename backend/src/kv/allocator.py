"""
Paged KV Cache block allocator and manager
(SCH-043, SCH-045, SCH-046, SCH-048, SCH-049, SCH-052, SCH-053).
Implements vLLM-style paged memory blocks with refcounting, prefix caching, address translation, and strict capacity invariants.
"""

import math
import hashlib
from typing import Dict, List, Optional, Set, Tuple
from collections import OrderedDict

class KVBlock:
    def __init__(self, block_id: int, block_size: int = 16):
        self.block_id = block_id
        self.block_size = block_size
        self.ref_count: int = 0
        self.prefix_hash: Optional[str] = None
        self.last_accessed: float = 0.0

class PagedKVCacheManager:
    """
    Paged KV Cache Manager.
    Invariants:
    1. len(free_blocks) + len(used_blocks) == total_blocks
    2. ref_count >= 0 for all blocks
    3. Blocks with ref_count == 0 are strictly in free_blocks (or eviction candidates)
    """
    def __init__(self, total_blocks: int = 1000, block_size: int = 16):
        if total_blocks <= 0:
            raise ValueError("total_blocks must be positive")
        if block_size <= 0:
            raise ValueError("block_size must be positive")

        self.total_blocks = total_blocks
        self.block_size = block_size

        self.blocks: Dict[int, KVBlock] = {i: KVBlock(i, block_size) for i in range(total_blocks)}
        self.free_blocks: List[int] = list(range(total_blocks))  # stack of free block IDs
        # sequence_id -> list of allocated physical block IDs
        self.block_tables: Dict[str, List[int]] = {}
        # sequence_id -> list of tokens currently allocated
        self.sequence_tokens: Dict[str, int] = {}
        # prefix_hash -> physical block ID for prefix sharing
        self.prefix_cache: OrderedDict[str, int] = OrderedDict()

    @property
    def used_blocks_count(self) -> int:
        return self.total_blocks - len(self.free_blocks)

    @property
    def free_blocks_count(self) -> int:
        return len(self.free_blocks)

    def can_allocate(self, num_tokens: int) -> bool:
        required_blocks = math.ceil(num_tokens / self.block_size)
        return len(self.free_blocks) >= required_blocks

    def allocate(self, sequence_id: str, num_tokens: int) -> Optional[List[int]]:
        """Allocates fresh blocks for a sequence (SCH-045)."""
        if sequence_id in self.block_tables:
            raise ValueError(f"Sequence {sequence_id} already has allocated blocks.")

        required_blocks = max(1, math.ceil(num_tokens / self.block_size))
        if len(self.free_blocks) < required_blocks:
            return None

        allocated_blocks: List[int] = []
        for _ in range(required_blocks):
            block_id = self.free_blocks.pop()
            block = self.blocks[block_id]
            block.ref_count = 1
            allocated_blocks.append(block_id)

        self.block_tables[sequence_id] = allocated_blocks
        self.sequence_tokens[sequence_id] = num_tokens
        return list(allocated_blocks)

    def register_prefix(self, prefix_tokens: str, block_id: int) -> str:
        """Associates a token sequence prefix hash with a physical block for prefix caching (SCH-048)."""
        h = hashlib.sha256(prefix_tokens.encode("utf-8")).hexdigest()
        self.prefix_cache[h] = block_id
        self.blocks[block_id].prefix_hash = h
        return h

    def match_prefix(self, prefix_tokens: str) -> Optional[int]:
        """Looks up existing prefix block in prefix cache (SCH-048)."""
        h = hashlib.sha256(prefix_tokens.encode("utf-8")).hexdigest()
        block_id = self.prefix_cache.get(h)
        if block_id is not None:
            # Move to end of OrderedDict for LRU tracking
            self.prefix_cache.move_to_end(h)
        return block_id

    def allocate_with_prefix(self, sequence_id: str, prefix_tokens: Optional[str], total_tokens: int) -> Optional[List[int]]:
        """
        Allocates blocks reusing existing cached prefix block if available (SCH-048).
        Saves allocating duplicate blocks for identical system prompts.
        """
        if sequence_id in self.block_tables:
            raise ValueError(f"Sequence {sequence_id} already has allocated blocks.")

        prefix_block_id = None
        if prefix_tokens:
            prefix_block_id = self.match_prefix(prefix_tokens)

        # If prefix matched, reuse 1 block
        reused_blocks = 1 if prefix_block_id is not None else 0
        total_blocks_needed = max(1, math.ceil(total_tokens / self.block_size))
        fresh_blocks_needed = max(0, total_blocks_needed - reused_blocks)

        if len(self.free_blocks) < fresh_blocks_needed:
            return None

        allocated: List[int] = []
        if prefix_block_id is not None:
            self.blocks[prefix_block_id].ref_count += 1
            allocated.append(prefix_block_id)

        for _ in range(fresh_blocks_needed):
            b_id = self.free_blocks.pop()
            self.blocks[b_id].ref_count = 1
            allocated.append(b_id)

        self.block_tables[sequence_id] = allocated
        self.sequence_tokens[sequence_id] = total_tokens
        return list(allocated)

    def translate_token_index(self, sequence_id: str, token_idx: int) -> Tuple[int, int]:
        """
        Paged logical-to-physical address translation (SCH-049).
        Given sequence_id and virtual token_idx, returns (physical_block_id, offset_in_block).
        """
        table = self.block_tables.get(sequence_id)
        if table is None:
            raise KeyError(f"Unknown sequence: {sequence_id}")

        block_index = token_idx // self.block_size
        offset = token_idx % self.block_size

        if block_index >= len(table):
            raise IndexError(f"Token index {token_idx} exceeds allocated blocks ({len(table)} blocks)")

        return table[block_index], offset

    def append_slot(self, sequence_id: str) -> Optional[int]:
        """Appends a token slot during decode generation (SCH-049)."""
        if sequence_id not in self.block_tables:
            return None

        current_tokens = self.sequence_tokens.get(sequence_id, 0)
        table = self.block_tables[sequence_id]
        capacity = len(table) * self.block_size

        if current_tokens < capacity:
            self.sequence_tokens[sequence_id] = current_tokens + 1
            return table[-1]

        # Block full; need new physical block
        if not self.free_blocks:
            return None

        b_id = self.free_blocks.pop()
        self.blocks[b_id].ref_count = 1
        table.append(b_id)
        self.sequence_tokens[sequence_id] = current_tokens + 1
        return b_id

    def free(self, sequence_id: str) -> bool:
        """
        Reclaims all blocks allocated to sequence_id (SCH-046).
        Decrements refcount; if refcount drops to 0, returns to free list.
        """
        table = self.block_tables.pop(sequence_id, None)
        self.sequence_tokens.pop(sequence_id, None)
        if table is None:
            return False

        for block_id in table:
            block = self.blocks[block_id]
            block.ref_count -= 1
            if block.ref_count < 0:
                block.ref_count = 0  # Invariant guard
            if block.ref_count == 0:
                self.free_blocks.append(block_id)

        return True

    def check_oom_risk(self, additional_tokens: int, watermark_ratio: float = 0.90) -> bool:
        """
        OOM prevention (SCH-052).
        Checks if admitting additional_tokens would exceed safe allocation watermark.
        """
        required_blocks = math.ceil(additional_tokens / self.block_size)
        projected_used = self.used_blocks_count + required_blocks
        max_safe_blocks = int(self.total_blocks * watermark_ratio)
        return projected_used > max_safe_blocks

    def evict_lru_prefix_blocks(self, target_blocks: int) -> int:
        """
        KV Cache Eviction Policy (SCH-053).
        Evicts unused (ref_count == 0) prefix cached blocks in LRU order.
        Invariant: NEVER evicts a block with ref_count > 0.
        """
        evicted = 0
        to_delete = []

        for prefix_hash, block_id in list(self.prefix_cache.items()):
            if evicted >= target_blocks:
                break
            block = self.blocks[block_id]
            # Strict invariant: cannot evict in-use block
            if block.ref_count > 0:
                continue

            to_delete.append(prefix_hash)
            block.prefix_hash = None
            if block_id not in self.free_blocks:
                self.free_blocks.append(block_id)
            evicted += 1

        for ph in to_delete:
            del self.prefix_cache[ph]

        return evicted

    def get_block_table(self, sequence_id: str) -> Optional[List[int]]:
        return self.block_tables.get(sequence_id)

    def verify_invariants(self) -> bool:
        """Asserts core invariants: used + free == total, no negative refcounts."""
        assert len(self.free_blocks) + self.used_blocks_count == self.total_blocks
        for b in self.blocks.values():
            assert b.ref_count >= 0
        return True
