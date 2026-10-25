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
async def test_SCH_024_memory_admission_control(async_session):
    sim_devices = [
        {
            "gpu_id": "gpu-adm-1",
            "device_name": "NVIDIA L4",
            "total_memory_bytes": 24000,
            "allocated_memory_bytes": 4000,  # 20,000 free, safe free = 20,000 * 0.95 = 19,000
            "utilization_pct": 20.0,
            "temperature_c": 50.0,
            "is_healthy": True
        }
    ]
    mgr = GPUManager(async_session, telemetry_adapter=NVMLTelemetryAdapter(simulated_devices=sim_devices))
    await mgr.sync_inventory()

    # Admissible: 10,000 bytes <= 19,000 safe free
    res1 = await mgr.check_memory_admission(required_bytes=10000)
    assert res1["admitted"] is True
    assert res1["gpu_id"] == "gpu-adm-1"

    # Inadmissible: 21,000 bytes > 19,000 safe free -> rejected
    res2 = await mgr.check_memory_admission(required_bytes=21000)
    assert res2["admitted"] is False
    assert "Insufficient GPU memory" in res2["reason"]
