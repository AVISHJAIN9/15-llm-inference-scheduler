"""
KV Cache Capacity Tracking and Monitoring (SCH-044).
Monitors physical cache block utilization and persists capacity state to SQL store.
"""

import uuid
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from sqlalchemy import Column, String, Integer, Float, DateTime, select
from sqlalchemy.ext.asyncio import AsyncSession
from db.database import Base
from kv.allocator import PagedKVCacheManager


class KVCacheCapacityRecord(Base):
    __tablename__ = "kv_cache_capacity_records"

    snapshot_id = Column(String(64), primary_key=True)
    worker_id = Column(String(64), nullable=False, index=True)
    total_blocks = Column(Integer, nullable=False)
    used_blocks = Column(Integer, nullable=False)
    free_blocks = Column(Integer, nullable=False)
    block_size_tokens = Column(Integer, default=16, nullable=False)
    utilization_pct = Column(Float, default=0.0, nullable=False)
    recorded_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "snapshot_id": self.snapshot_id,
            "worker_id": self.worker_id,
            "total_blocks": self.total_blocks,
            "used_blocks": self.used_blocks,
            "free_blocks": self.free_blocks,
            "block_size_tokens": self.block_size_tokens,
            "utilization_pct": self.utilization_pct,
            "recorded_at": self.recorded_at.isoformat() if self.recorded_at else None,
        }


class KVCacheCapacityTracker:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def record_snapshot(
        self,
        worker_id: str,
        cache_manager: PagedKVCacheManager
    ) -> KVCacheCapacityRecord:
        """Captures real-time block allocation metrics from a PagedKVCacheManager and persists to SQL (SCH-044)."""
        snapshot_id = f"snap-{uuid.uuid4().hex[:12]}"
        total = cache_manager.total_blocks
        used = cache_manager.used_blocks_count
        free = cache_manager.free_blocks_count
        utilization = (used / total * 100.0) if total > 0 else 0.0
        now = datetime.now(timezone.utc)

        record = KVCacheCapacityRecord(
            snapshot_id=snapshot_id,
            worker_id=worker_id,
            total_blocks=total,
            used_blocks=used,
            free_blocks=free,
            block_size_tokens=cache_manager.block_size,
            utilization_pct=round(utilization, 2),
            recorded_at=now
        )
        self.session.add(record)
        await self.session.commit()
        return record

    async def get_latest_snapshot(self, worker_id: str) -> Optional[KVCacheCapacityRecord]:
        """Returns the most recent capacity snapshot for the specified worker (SCH-044)."""
        stmt = (
            select(KVCacheCapacityRecord)
            .where(KVCacheCapacityRecord.worker_id == worker_id)
            .order_by(KVCacheCapacityRecord.recorded_at.desc())
            .limit(1)
        )
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def get_snapshot_history(self, worker_id: str, limit: int = 50) -> List[KVCacheCapacityRecord]:
        """Returns chronological capacity snapshots for trending and analytics (SCH-044)."""
        stmt = (
            select(KVCacheCapacityRecord)
            .where(KVCacheCapacityRecord.worker_id == worker_id)
            .order_by(KVCacheCapacityRecord.recorded_at.asc())
            .limit(limit)
        )
        res = await self.session.execute(stmt)
        return list(res.scalars().all())
