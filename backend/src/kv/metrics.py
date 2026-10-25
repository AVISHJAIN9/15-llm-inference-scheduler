"""
KV Cache Hit-Rate Metrics and Observability (SCH-056).
Tracks prefix cache lookups (hits/misses), computes rolling and windowed hit rates,
and persists telemetry snapshots into SQL store.
"""

import uuid
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from sqlalchemy import Column, String, Integer, Float, DateTime, select
from sqlalchemy.ext.asyncio import AsyncSession
from db.database import Base


class KVCacheHitRateRecord(Base):
    __tablename__ = "kv_cache_hit_rate_metrics"

    metric_id = Column(String(64), primary_key=True)
    worker_id = Column(String(64), nullable=False, index=True)
    window_seconds = Column(Integer, default=60, nullable=False)
    total_lookups = Column(Integer, nullable=False)
    hits = Column(Integer, nullable=False)
    misses = Column(Integer, nullable=False)
    hit_rate_pct = Column(Float, nullable=False)
    tokens_saved = Column(Integer, default=0, nullable=False)
    recorded_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "metric_id": self.metric_id,
            "worker_id": self.worker_id,
            "window_seconds": self.window_seconds,
            "total_lookups": self.total_lookups,
            "hits": self.hits,
            "misses": self.misses,
            "hit_rate_pct": self.hit_rate_pct,
            "tokens_saved": self.tokens_saved,
            "recorded_at": self.recorded_at.isoformat() if self.recorded_at else None,
        }


class KVCacheMetricsCollector:
    def __init__(self, session: AsyncSession):
        self.session = session
        # In-memory accumulator per worker: {worker_id: {"hits": int, "misses": int, "tokens_saved": int}}
        self._counters: Dict[str, Dict[str, int]] = {}

    def record_lookup(self, worker_id: str, is_hit: bool, tokens_saved: int = 0) -> None:
        """Records a cache lookup event for the worker (SCH-056)."""
        worker_counter = self._counters.setdefault(worker_id, {"hits": 0, "misses": 0, "tokens_saved": 0})
        if is_hit:
            worker_counter["hits"] += 1
            worker_counter["tokens_saved"] += tokens_saved
        else:
            worker_counter["misses"] += 1

    def get_realtime_hit_rate(self, worker_id: str) -> float:
        """Calculates current hit-rate percentage from active lookups (SCH-056)."""
        counter = self._counters.get(worker_id)
        if not counter:
            return 0.0

        hits = counter["hits"]
        total = hits + counter["misses"]
        return round((hits / total * 100.0), 2) if total > 0 else 0.0

    async def persist_metrics_window(
        self,
        worker_id: str,
        window_seconds: int = 60
    ) -> KVCacheHitRateRecord:
        """Persists windowed hit-rate metrics snapshot to SQL store (SCH-056)."""
        counter = self._counters.get(worker_id, {"hits": 0, "misses": 0, "tokens_saved": 0})
        hits = counter["hits"]
        misses = counter["misses"]
        total = hits + misses
        hit_rate = round((hits / total * 100.0), 2) if total > 0 else 0.0
        tokens_saved = counter["tokens_saved"]

        metric_id = f"hit-{uuid.uuid4().hex[:12]}"
        now = datetime.now(timezone.utc)
        record = KVCacheHitRateRecord(
            metric_id=metric_id,
            worker_id=worker_id,
            window_seconds=window_seconds,
            total_lookups=total,
            hits=hits,
            misses=misses,
            hit_rate_pct=hit_rate,
            tokens_saved=tokens_saved,
            recorded_at=now
        )
        self.session.add(record)
        await self.session.commit()
        return record

    async def get_historical_metrics(
        self,
        worker_id: str,
        limit: int = 10
    ) -> List[KVCacheHitRateRecord]:
        """Queries historical hit rate snapshots for a worker (SCH-056)."""
        stmt = (
            select(KVCacheHitRateRecord)
            .where(KVCacheHitRateRecord.worker_id == worker_id)
            .order_by(KVCacheHitRateRecord.recorded_at.desc())
            .limit(limit)
        )
        res = await self.session.execute(stmt)
        return list(res.scalars().all())
