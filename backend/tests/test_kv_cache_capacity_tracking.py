import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from db.database import Base
from kv.allocator import PagedKVCacheManager
from kv.capacity import KVCacheCapacityTracker, KVCacheCapacityRecord

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
async def test_SCH_044_kv_cache_capacity_tracking(async_session):
    """
    SCH-044: KV-cache capacity tracking (BE+DB).
    Accurately tracks active and available KV-cache memory blocks, token capacity,
    and utilization percentage, persisting capacity snapshots to SQL store.
    """
    cache_mgr = PagedKVCacheManager(total_blocks=100, block_size=16)
    tracker = KVCacheCapacityTracker(async_session)

    # 1. Initial empty capacity snapshot
    snap1 = await tracker.record_snapshot(worker_id="worker-gpu-0", cache_manager=cache_mgr)
    assert snap1.worker_id == "worker-gpu-0"
    assert snap1.total_blocks == 100
    assert snap1.used_blocks == 0
    assert snap1.free_blocks == 100
    assert snap1.block_size_tokens == 16
    assert snap1.utilization_pct == 0.0

    # 2. Allocate 32 blocks (512 tokens)
    allocated = cache_mgr.allocate(sequence_id="seq-1", num_tokens=512)
    assert len(allocated) == 32
    assert cache_mgr.used_blocks_count == 32
    assert cache_mgr.free_blocks_count == 68

    # Record updated snapshot
    snap2 = await tracker.record_snapshot(worker_id="worker-gpu-0", cache_manager=cache_mgr)
    assert snap2.used_blocks == 32
    assert snap2.free_blocks == 68
    assert abs(snap2.utilization_pct - 32.0) < 0.01

    # 3. Retrieve latest snapshot from SQL database
    latest = await tracker.get_latest_snapshot("worker-gpu-0")
    assert latest is not None
    assert latest.used_blocks == 32
    assert latest.free_blocks == 68
    assert abs(latest.utilization_pct - 32.0) < 0.01

    # 4. Deallocate sequence and verify capacity recovery tracking
    cache_mgr.free("seq-1")
    assert cache_mgr.used_blocks_count == 0
    assert cache_mgr.free_blocks_count == 100

    snap3 = await tracker.record_snapshot(worker_id="worker-gpu-0", cache_manager=cache_mgr)
    assert snap3.used_blocks == 0
    assert snap3.free_blocks == 100
    assert snap3.utilization_pct == 0.0
