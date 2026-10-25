"""
Per-Request KV Cache Budget and Enforcement (SCH-054).
Enforces strict upper bounds on memory block allocations per request.
Budget breach rejects/queues, never over-commits (Invariant P15 §9).
Persists allocation states and breach telemetry to SQL store.
"""

import math
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from sqlalchemy import Column, String, Integer, Boolean, DateTime, select
from sqlalchemy.ext.asyncio import AsyncSession
from db.database import Base
from kv.allocator import PagedKVCacheManager


class BudgetExceededError(Exception):
    """Raised when a request attempts to allocate more KV blocks than its configured budget."""
    pass


class RequestCacheBudgetRecord(Base):
    __tablename__ = "request_cache_budgets"

    request_id = Column(String(64), primary_key=True)
    max_budget_blocks = Column(Integer, nullable=False)
    allocated_blocks = Column(Integer, default=0, nullable=False)
    status = Column(String(32), default="ACTIVE", nullable=False)  # ACTIVE, RELEASED
    is_breached = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "request_id": self.request_id,
            "max_budget_blocks": self.max_budget_blocks,
            "allocated_blocks": self.allocated_blocks,
            "status": self.status,
            "is_breached": self.is_breached,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class RequestCacheBudgetManager:
    def __init__(self, session: AsyncSession, cache_manager: Optional[PagedKVCacheManager] = None):
        self.session = session
        self.cache_mgr = cache_manager or PagedKVCacheManager()

    async def set_request_budget(self, request_id: str, max_budget_blocks: int) -> RequestCacheBudgetRecord:
        """Configures the maximum cache block budget for an inference request (SCH-054)."""
        if max_budget_blocks <= 0:
            raise ValueError("max_budget_blocks must be positive")

        stmt = select(RequestCacheBudgetRecord).where(RequestCacheBudgetRecord.request_id == request_id)
        res = await self.session.execute(stmt)
        record = res.scalar_one_or_none()

        now = datetime.now(timezone.utc)
        if record:
            record.max_budget_blocks = max_budget_blocks
            record.updated_at = now
        else:
            record = RequestCacheBudgetRecord(
                request_id=request_id,
                max_budget_blocks=max_budget_blocks,
                allocated_blocks=0,
                status="ACTIVE",
                is_breached=False,
                created_at=now,
                updated_at=now
            )
            self.session.add(record)

        await self.session.commit()
        return record

    async def allocate_within_budget(self, request_id: str, num_tokens: int) -> List[int]:
        """
        Allocates blocks for a sequence strictly verifying against per-request budget (SCH-054).
        Breaches reject and never over-commit.
        """
        record = await self.get_request_budget(request_id)
        if not record:
            raise ValueError(f"No budget configured for request '{request_id}'")

        blocks_needed = max(1, math.ceil(num_tokens / self.cache_mgr.block_size))
        if record.allocated_blocks + blocks_needed > record.max_budget_blocks:
            record.is_breached = True
            record.updated_at = datetime.now(timezone.utc)
            await self.session.commit()
            raise BudgetExceededError(
                f"Requested {blocks_needed} blocks exceeds per-request budget limit "
                f"({record.allocated_blocks}/{record.max_budget_blocks} allocated)"
            )

        allocated = self.cache_mgr.allocate(sequence_id=request_id, num_tokens=num_tokens)
        if allocated is None:
            raise MemoryError(f"Insufficient global physical blocks for request '{request_id}'")

        record.allocated_blocks += len(allocated)
        record.updated_at = datetime.now(timezone.utc)
        await self.session.commit()
        return allocated

    async def allocate_additional_blocks(self, request_id: str, num_additional_blocks: int) -> List[int]:
        """
        Allocates additional blocks for expanding context (decoding) within budget (SCH-054).
        """
        record = await self.get_request_budget(request_id)
        if not record:
            raise ValueError(f"No budget configured for request '{request_id}'")

        if record.allocated_blocks + num_additional_blocks > record.max_budget_blocks:
            record.is_breached = True
            record.updated_at = datetime.now(timezone.utc)
            await self.session.commit()
            raise BudgetExceededError(
                f"Allocating {num_additional_blocks} additional blocks exceeds per-request budget "
                f"({record.allocated_blocks}/{record.max_budget_blocks} allocated)"
            )

        if len(self.cache_mgr.free_blocks) < num_additional_blocks:
            raise MemoryError("Insufficient physical free blocks in cache")

        new_blocks: List[int] = []
        for _ in range(num_additional_blocks):
            b_id = self.cache_mgr.free_blocks.pop()
            self.cache_mgr.blocks[b_id].ref_count = 1
            new_blocks.append(b_id)

        # Append to existing table
        current_table = self.cache_mgr.block_tables.setdefault(request_id, [])
        current_table.extend(new_blocks)

        record.allocated_blocks += len(new_blocks)
        record.updated_at = datetime.now(timezone.utc)
        await self.session.commit()
        return new_blocks

    async def get_request_budget(self, request_id: str) -> Optional[RequestCacheBudgetRecord]:
        """Queries budget status and allocation for a request from SQL store (SCH-054)."""
        stmt = select(RequestCacheBudgetRecord).where(RequestCacheBudgetRecord.request_id == request_id)
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def release_request(self, request_id: str) -> bool:
        """Releases all allocated cache blocks and marks budget released (SCH-054)."""
        record = await self.get_request_budget(request_id)
        if not record or record.status == "RELEASED":
            return False

        if request_id in self.cache_mgr.block_tables:
            self.cache_mgr.free(request_id)

        record.allocated_blocks = 0
        record.status = "RELEASED"
        record.updated_at = datetime.now(timezone.utc)
        await self.session.commit()
        return True
