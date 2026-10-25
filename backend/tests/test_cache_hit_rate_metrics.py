import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from db.database import Base
from kv.metrics import KVCacheMetricsCollector, KVCacheHitRateRecord

@pytest_asyncio.fixture
async def async_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with session_maker() as session:
        yield session
    await engine.dispose()

@pytest.mark.asyncio
async def test_SCH_056_cache_hit_rate_metrics(async_session):
    """
    SCH-056: Cache hit-rate metrics (BE+DB).
    Records prefix lookup hits and misses, calculates windowed hit-rate percentages,
    and persists telemetry snapshots into SQL store.
    """
    collector = KVCacheMetricsCollector(async_session)

    # 1. Initially zero lookups -> 0.0% hit rate
    initial_rate = collector.get_realtime_hit_rate("worker-1")
    assert initial_rate == 0.0

    # 2. Record 7 hits and 3 misses (10 total -> 70% hit rate)
    for _ in range(7):
        collector.record_lookup("worker-1", is_hit=True, tokens_saved=16)
    for _ in range(3):
        collector.record_lookup("worker-1", is_hit=False)

    rate = collector.get_realtime_hit_rate("worker-1")
    assert abs(rate - 70.0) < 0.01

    # 3. Persist metrics window into SQL database
    metric_record = await collector.persist_metrics_window("worker-1", window_seconds=60)
    assert metric_record.worker_id == "worker-1"
    assert metric_record.total_lookups == 10
    assert metric_record.hits == 7
    assert metric_record.misses == 3
    assert abs(metric_record.hit_rate_pct - 70.0) < 0.01

    # 4. Query historical metrics from SQL
    history = await collector.get_historical_metrics("worker-1", limit=5)
    assert len(history) == 1
    assert history[0].total_lookups == 10
    assert abs(history[0].hit_rate_pct - 70.0) < 0.01
