"""
KV Cache Prefix Reuse and Sharing (SCH-047).
Identifies shared prompt prefixes across requests, reuses pre-computed KV blocks,
and records reuse metrics, block savings, and avoided computation in SQL store.
"""

import uuid
import hashlib
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from sqlalchemy import Column, String, Integer, Float, DateTime, select
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from db.database import Base
from kv.allocator import PagedKVCacheManager


class KVCacheReuseRecord(Base):
    __tablename__ = "kv_cache_reuse_records"

    reuse_id = Column(String(64), primary_key=True)
    request_id = Column(String(64), nullable=False, index=True)
    tenant_id = Column(String(64), nullable=False, index=True)
    prefix_hash = Column(String(64), nullable=False, index=True)
    reused_blocks_count = Column(Integer, default=0, nullable=False)
    reused_tokens_count = Column(Integer, default=0, nullable=False)
    total_tokens = Column(Integer, nullable=False)
    saved_computation_pct = Column(Float, default=0.0, nullable=False)
    reused_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "reuse_id": self.reuse_id,
            "request_id": self.request_id,
            "tenant_id": self.tenant_id,
            "prefix_hash": self.prefix_hash,
            "reused_blocks_count": self.reused_blocks_count,
            "reused_tokens_count": self.reused_tokens_count,
            "total_tokens": self.total_tokens,
            "saved_computation_pct": self.saved_computation_pct,
            "reused_at": self.reused_at.isoformat() if self.reused_at else None,
        }


class ReuseAllocationResult(BaseModel):
    reuse_id: str
    request_id: str
    allocated_blocks: List[int]
    reused_blocks_count: int
    reused_tokens_count: int
    saved_computation_pct: float


class KVCacheReuseManager:
    def __init__(self, session: AsyncSession, cache_manager: Optional[PagedKVCacheManager] = None):
        self.session = session
        self.cache_mgr = cache_manager or PagedKVCacheManager()

    async def allocate_with_reuse(
        self,
        request_id: str,
        tenant_id: str,
        prefix_text: Optional[str],
        total_tokens: int
    ) -> ReuseAllocationResult:
        """
        Allocates KV cache blocks, reusing pre-computed prefix blocks when identical
        prefix text is already resident in cache (SCH-047).
        """
        prefix_hash = hashlib.sha256((prefix_text or "").encode("utf-8")).hexdigest()
        matched_block = self.cache_mgr.match_prefix(prefix_text) if prefix_text else None

        if matched_block is not None:
            # Reusing matched prefix block
            allocated = self.cache_mgr.allocate_with_prefix(
                sequence_id=request_id,
                prefix_tokens=prefix_text,
                total_tokens=total_tokens
            )
            if allocated is None:
                raise MemoryError(f"Insufficient free blocks to allocate {total_tokens} tokens")

            reused_blocks = 1
            reused_tokens = min(self.cache_mgr.block_size, total_tokens)
            saved_pct = round((reused_tokens / total_tokens) * 100.0, 2)
        else:
            # Fresh allocation
            allocated = self.cache_mgr.allocate(sequence_id=request_id, num_tokens=total_tokens)
            if allocated is None:
                raise MemoryError(f"Insufficient free blocks to allocate {total_tokens} tokens")

            reused_blocks = 0
            reused_tokens = 0
            saved_pct = 0.0

            # Register first block as cached prefix for future reuse
            if prefix_text and len(allocated) > 0:
                self.cache_mgr.register_prefix(prefix_text, allocated[0])

        reuse_id = f"reuse-{uuid.uuid4().hex[:12]}"
        now = datetime.now(timezone.utc)
        record = KVCacheReuseRecord(
            reuse_id=reuse_id,
            request_id=request_id,
            tenant_id=tenant_id,
            prefix_hash=prefix_hash,
            reused_blocks_count=reused_blocks,
            reused_tokens_count=reused_tokens,
            total_tokens=total_tokens,
            saved_computation_pct=saved_pct,
            reused_at=now
        )
        self.session.add(record)
        await self.session.commit()

        return ReuseAllocationResult(
            reuse_id=reuse_id,
            request_id=request_id,
            allocated_blocks=allocated,
            reused_blocks_count=reused_blocks,
            reused_tokens_count=reused_tokens,
            saved_computation_pct=saved_pct
        )

    async def get_reuse_record(self, reuse_id: str) -> Optional[KVCacheReuseRecord]:
        """Fetches a specific reuse record by ID (SCH-047)."""
        stmt = select(KVCacheReuseRecord).where(KVCacheReuseRecord.reuse_id == reuse_id)
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def get_reuse_metrics(self, tenant_id: Optional[str] = None) -> Dict[str, Any]:
        """Calculates aggregated KV cache reuse statistics and savings (SCH-047)."""
        stmt = select(KVCacheReuseRecord)
        if tenant_id:
            stmt = stmt.where(KVCacheReuseRecord.tenant_id == tenant_id)

        res = await self.session.execute(stmt)
        records = list(res.scalars().all())

        # Filter only events where reuse actually occurred
        reused_events = [r for r in records if r.reused_blocks_count > 0]

        total_saved_blocks = sum(r.reused_blocks_count for r in reused_events)
        total_saved_tokens = sum(r.reused_tokens_count for r in reused_events)
        avg_saved_pct = (
            sum(r.saved_computation_pct for r in reused_events) / len(reused_events)
            if reused_events else 0.0
        )

        return {
            "tenant_id": tenant_id,
            "total_requests": len(records),
            "total_reuse_events": len(reused_events),
            "total_saved_blocks": total_saved_blocks,
            "total_saved_tokens": total_saved_tokens,
            "avg_saved_computation_pct": round(avg_saved_pct, 2)
        }
