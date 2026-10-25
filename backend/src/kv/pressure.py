"""
KV Cache Memory Pressure Detection and Mitigation (SCH-051).
Monitors KV memory usage against watermarks, evaluates pressure tiers (NORMAL, HIGH, CRITICAL),
recommends throttling and preemption actions, and persists telemetry in SQL store.
"""

import uuid
from enum import Enum
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from sqlalchemy import Column, String, Integer, Float, DateTime, select
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from db.database import Base
from kv.allocator import PagedKVCacheManager


class PressureLevel(str, Enum):
    NORMAL = "NORMAL"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class PressureAction(str, Enum):
    NONE = "NONE"
    THROTTLE_ADMISSION = "THROTTLE_ADMISSION"
    TRIGGER_EVICTION = "TRIGGER_EVICTION"


class KVMemoryPressureRecord(Base):
    __tablename__ = "kv_memory_pressure_records"

    event_id = Column(String(64), primary_key=True)
    worker_id = Column(String(64), nullable=False, index=True)
    total_blocks = Column(Integer, nullable=False)
    used_blocks = Column(Integer, nullable=False)
    free_blocks = Column(Integer, nullable=False)
    utilization_pct = Column(Float, nullable=False)
    pressure_level = Column(String(32), nullable=False)
    recommended_action = Column(String(64), nullable=False)
    recorded_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "worker_id": self.worker_id,
            "total_blocks": self.total_blocks,
            "used_blocks": self.used_blocks,
            "free_blocks": self.free_blocks,
            "utilization_pct": self.utilization_pct,
            "pressure_level": self.pressure_level,
            "recommended_action": self.recommended_action,
            "recorded_at": self.recorded_at.isoformat() if self.recorded_at else None,
        }


class PressureEvaluationResult(BaseModel):
    event_id: str
    worker_id: str
    total_blocks: int
    used_blocks: int
    free_blocks: int
    utilization_pct: float
    pressure_level: PressureLevel
    recommended_action: PressureAction


class MemoryPressureDetector:
    def __init__(
        self,
        session: AsyncSession,
        high_watermark_pct: float = 75.0,
        critical_watermark_pct: float = 90.0
    ):
        if not (0.0 < high_watermark_pct < critical_watermark_pct <= 100.0):
            raise ValueError("Watermarks must satisfy 0 < high < critical <= 100")

        self.session = session
        self.high_watermark_pct = high_watermark_pct
        self.critical_watermark_pct = critical_watermark_pct

    async def evaluate_and_record_pressure(
        self,
        worker_id: str,
        cache_manager: PagedKVCacheManager
    ) -> PressureEvaluationResult:
        """
        Evaluates cache memory pressure against watermarks and records incident in SQL (SCH-051).
        """
        total = cache_manager.total_blocks
        used = cache_manager.used_blocks_count
        free = cache_manager.free_blocks_count
        utilization = (used / total * 100.0) if total > 0 else 0.0

        if utilization >= self.critical_watermark_pct:
            level = PressureLevel.CRITICAL
            action = PressureAction.TRIGGER_EVICTION
        elif utilization >= self.high_watermark_pct:
            level = PressureLevel.HIGH
            action = PressureAction.THROTTLE_ADMISSION
        else:
            level = PressureLevel.NORMAL
            action = PressureAction.NONE

        event_id = f"press-{uuid.uuid4().hex[:12]}"
        now = datetime.now(timezone.utc)
        record = KVMemoryPressureRecord(
            event_id=event_id,
            worker_id=worker_id,
            total_blocks=total,
            used_blocks=used,
            free_blocks=free,
            utilization_pct=round(utilization, 2),
            pressure_level=level.value,
            recommended_action=action.value,
            recorded_at=now
        )
        self.session.add(record)
        await self.session.commit()

        return PressureEvaluationResult(
            event_id=event_id,
            worker_id=worker_id,
            total_blocks=total,
            used_blocks=used,
            free_blocks=free,
            utilization_pct=round(utilization, 2),
            pressure_level=level,
            recommended_action=action
        )

    async def get_latest_pressure_event(self, worker_id: str) -> Optional[KVMemoryPressureRecord]:
        """Returns the most recent memory pressure event for a worker (SCH-051)."""
        stmt = (
            select(KVMemoryPressureRecord)
            .where(KVMemoryPressureRecord.worker_id == worker_id)
            .order_by(KVMemoryPressureRecord.recorded_at.desc())
            .limit(1)
        )
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()
