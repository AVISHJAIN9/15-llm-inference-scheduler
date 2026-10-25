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
async def test_SCH_015_gpu_inventory_real_and_simulated(async_session):
    # 1. Test genuine adapter when no physical GPU is present -> honestly reports 0 devices
    real_adapter = NVMLTelemetryAdapter()
    if not real_adapter.is_hardware_available():
        mgr_real = GPUManager(async_session, telemetry_adapter=real_adapter)
        devices = await mgr_real.sync_inventory(node_id="node-real")
        assert len(devices) == 0

    # 2. Test inventory with simulated hardware telemetry injection per spec §9 P15
    sim_devices = [
        {
            "gpu_id": "node-1-gpu-0",
            "device_name": "NVIDIA A100-SXM4-80GB",
            "total_memory_bytes": 85899345920,
            "allocated_memory_bytes": 10737418240,
            "utilization_pct": 35.0,
            "temperature_c": 52.0,
            "is_healthy": True
        },
        {
            "gpu_id": "node-1-gpu-1",
            "device_name": "NVIDIA A100-SXM4-80GB",
            "total_memory_bytes": 85899345920,
            "allocated_memory_bytes": 21474836480,
            "utilization_pct": 55.0,
            "temperature_c": 58.0,
            "is_healthy": True
        }
    ]
    sim_adapter = NVMLTelemetryAdapter(simulated_devices=sim_devices)
    mgr = GPUManager(async_session, telemetry_adapter=sim_adapter)

    synced = await mgr.sync_inventory(node_id="node-1")
    assert len(synced) == 2
    assert synced[0].gpu_id == "node-1-gpu-0"
    assert synced[0].total_memory_bytes == 85899345920

    # Read from database to verify persistence
    db_devices = await mgr.list_devices()
    assert len(db_devices) == 2
    assert db_devices[0].device_name == "NVIDIA A100-SXM4-80GB"
