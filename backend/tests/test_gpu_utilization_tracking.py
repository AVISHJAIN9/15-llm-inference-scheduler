import pytest
import pytest_asyncio
from datetime import datetime, timezone, timedelta
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
async def test_SCH_018_gpu_utilization_tracking(async_session):
    """
    SCH-018: GPU utilization tracking (BE+DB).
    Records real-time GPU compute and memory utilization telemetry into SQL store,
    maintains historical time-series samples, and computes aggregated metrics (min, max, avg).
    """
    sim_devices = [
        {
            "gpu_id": "gpu-prod-0",
            "device_name": "NVIDIA H100",
            "total_memory_bytes": 85899345920,
            "allocated_memory_bytes": 21474836480,
            "utilization_pct": 45.0,
            "temperature_c": 52.0,
            "is_healthy": True
        }
    ]
    telemetry = NVMLTelemetryAdapter(simulated_devices=sim_devices)
    manager = GPUManager(async_session, telemetry_adapter=telemetry)
    await manager.sync_inventory(node_id="node-prod")

    now = datetime.now(timezone.utc)
    # Record multiple utilization samples across time
    samples = [
        (30.0, 25.0, 50.0, now - timedelta(minutes=4)),
        (50.0, 40.0, 55.0, now - timedelta(minutes=3)),
        (80.0, 65.0, 62.0, now - timedelta(minutes=2)),
        (60.0, 50.0, 58.0, now - timedelta(minutes=1)),
    ]

    for compute_util, mem_util, temp, ts in samples:
        record = await manager.record_utilization_sample(
            gpu_id="gpu-prod-0",
            compute_util_pct=compute_util,
            memory_util_pct=mem_util,
            temperature_c=temp,
            timestamp=ts
        )
        assert record.gpu_id == "gpu-prod-0"
        assert record.compute_util_pct == compute_util

    # Query utilization history
    history = await manager.get_utilization_history("gpu-prod-0", limit=10)
    assert len(history) == 4
    assert history[0]["compute_util_pct"] == 30.0
    assert history[-1]["compute_util_pct"] == 60.0

    # Query summary metrics
    summary = await manager.get_utilization_summary("gpu-prod-0")
    assert summary["sample_count"] == 4
    assert summary["min_compute_pct"] == 30.0
    assert summary["max_compute_pct"] == 80.0
    # Average compute = (30 + 50 + 80 + 60) / 4 = 55.0
    assert abs(summary["avg_compute_pct"] - 55.0) < 0.01
    assert abs(summary["avg_memory_pct"] - 45.0) < 0.01

    # Verify device record reflects most recent utilization
    dev = await manager.get_device("gpu-prod-0")
    assert dev is not None
    assert dev.utilization_pct == 60.0
