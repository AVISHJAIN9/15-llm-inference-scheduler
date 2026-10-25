import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from db.database import Base
from gpu.manager import GPUManager
from gpu.telemetry import NVMLTelemetryAdapter

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
async def test_SCH_017_gpu_memory_tracking(async_session):
    sim_devices = [
        {
            "gpu_id": "gpu-tracking-1",
            "device_name": "NVIDIA H100",
            "total_memory_bytes": 1000,
            "allocated_memory_bytes": 200,
            "utilization_pct": 10.0,
            "temperature_c": 45.0,
            "is_healthy": True
        }
    ]
    mgr = GPUManager(async_session, telemetry_adapter=NVMLTelemetryAdapter(simulated_devices=sim_devices))
    await mgr.sync_inventory(node_id="node-track")

    dev = await mgr.get_device("gpu-tracking-1")
    assert dev.allocated_memory_bytes == 200
    assert dev.free_memory_bytes == 800

    # Allocate additional 300 bytes
    ok = await mgr.update_memory("gpu-tracking-1", delta_bytes=300)
    assert ok is True

    dev = await mgr.get_device("gpu-tracking-1")
    assert dev.allocated_memory_bytes == 500
    assert dev.free_memory_bytes == 500

    # Deallocate 100 bytes
    ok = await mgr.update_memory("gpu-tracking-1", delta_bytes=-100)
    assert ok is True
    dev = await mgr.get_device("gpu-tracking-1")
    assert dev.allocated_memory_bytes == 400
    assert dev.free_memory_bytes == 600

    # Attempt to exceed total memory capacity -> rejected
    overflow = await mgr.update_memory("gpu-tracking-1", delta_bytes=700)
    assert overflow is False
    dev = await mgr.get_device("gpu-tracking-1")
    assert dev.allocated_memory_bytes == 400
