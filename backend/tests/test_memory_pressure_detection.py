import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from db.database import Base
from kv.allocator import PagedKVCacheManager
from kv.pressure import MemoryPressureDetector, PressureLevel, PressureAction

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
async def test_SCH_051_memory_pressure_detection(async_session):
    """
    SCH-051: Memory pressure detection (BE+DB).
    Monitors KV cache allocation against multi-tiered watermarks, detects memory pressure
    (NORMAL -> HIGH -> CRITICAL), recommends proactive scheduler actions, and persists
    pressure events into SQL store.
    """
    cache_mgr = PagedKVCacheManager(total_blocks=100, block_size=16)
    detector = MemoryPressureDetector(
        session=async_session,
        high_watermark_pct=70.0,
        critical_watermark_pct=90.0
    )

    # 1. Low allocation (20% used) -> NORMAL pressure, action NONE
    cache_mgr.allocate(sequence_id="seq-1", num_tokens=320)  # 20 blocks
    p1 = await detector.evaluate_and_record_pressure("worker-gpu-0", cache_mgr)
    assert p1.pressure_level == PressureLevel.NORMAL
    assert p1.recommended_action == PressureAction.NONE
    assert p1.utilization_pct == 20.0

    # 2. Medium-high allocation (75% used) -> HIGH pressure, action THROTTLE_ADMISSION
    cache_mgr.allocate(sequence_id="seq-2", num_tokens=880)  # 55 additional blocks -> 75 total
    p2 = await detector.evaluate_and_record_pressure("worker-gpu-0", cache_mgr)
    assert p2.pressure_level == PressureLevel.HIGH
    assert p2.recommended_action == PressureAction.THROTTLE_ADMISSION
    assert p2.utilization_pct == 75.0

    # 3. Critical allocation (95% used) -> CRITICAL pressure, action TRIGGER_EVICTION
    cache_mgr.allocate(sequence_id="seq-3", num_tokens=320)  # 20 additional blocks -> 95 total
    p3 = await detector.evaluate_and_record_pressure("worker-gpu-0", cache_mgr)
    assert p3.pressure_level == PressureLevel.CRITICAL
    assert p3.recommended_action == PressureAction.TRIGGER_EVICTION
    assert p3.utilization_pct == 95.0

    # 4. Verify SQL persistence of latest pressure event
    latest_event = await detector.get_latest_pressure_event("worker-gpu-0")
    assert latest_event is not None
    assert latest_event.pressure_level == PressureLevel.CRITICAL.value
    assert latest_event.recommended_action == PressureAction.TRIGGER_EVICTION.value
    assert latest_event.utilization_pct == 95.0
