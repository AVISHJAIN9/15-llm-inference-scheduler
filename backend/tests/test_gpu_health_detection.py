import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from db.database import Base
from gpu.manager import GPUManager
from gpu.telemetry import NVMLTelemetryAdapter
from gpu.health import GPUHealthStatus, GPUHealthPolicy

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
async def test_SCH_016_gpu_health_detection(async_session):
    """
    SCH-016: GPU health detection.
    Detects hardware faults (thermal throttling/overheating, ECC errors, driver errors),
    updates device health status in SQL store, and marks unhealthy GPUs offline.
    """
    devices_data = [
        {
            "gpu_id": "gpu-normal",
            "device_name": "NVIDIA H100",
            "total_memory_bytes": 85899345920,
            "allocated_memory_bytes": 0,
            "utilization_pct": 20.0,
            "temperature_c": 55.0,
            "ecc_errors": 0,
            "is_healthy": True
        },
        {
            "gpu_id": "gpu-overheated",
            "device_name": "NVIDIA H100",
            "total_memory_bytes": 85899345920,
            "allocated_memory_bytes": 0,
            "utilization_pct": 98.0,
            "temperature_c": 92.0,  # Exceeds max 85.0C
            "ecc_errors": 0,
            "is_healthy": True
        },
        {
            "gpu_id": "gpu-ecc-fault",
            "device_name": "NVIDIA H100",
            "total_memory_bytes": 85899345920,
            "allocated_memory_bytes": 0,
            "utilization_pct": 10.0,
            "temperature_c": 50.0,
            "ecc_errors": 4,  # Uncorrectable ECC errors
            "is_healthy": True
        }
    ]

    telemetry = NVMLTelemetryAdapter(simulated_devices=devices_data)
    manager = GPUManager(async_session, telemetry_adapter=telemetry)

    # 1. Sync initial inventory into DB
    synced = await manager.sync_inventory(node_id="node-1")
    assert len(synced) == 3

    # 2. Run health detection evaluation
    policy = GPUHealthPolicy(max_temperature_c=85.0, max_ecc_errors=0)
    health_results = await manager.evaluate_and_update_health(policy=policy)

    assert len(health_results) == 3

    # Normal GPU remains healthy
    r_normal = next(r for r in health_results if r.gpu_id == "gpu-normal")
    assert r_normal.is_healthy is True
    assert r_normal.status == GPUHealthStatus.HEALTHY

    # Overheated GPU is detected and marked unhealthy
    r_overheated = next(r for r in health_results if r.gpu_id == "gpu-overheated")
    assert r_overheated.is_healthy is False
    assert r_overheated.status == GPUHealthStatus.OVERHEATED
    assert "temperature" in r_overheated.reason.lower()

    # ECC fault GPU is detected and marked unhealthy
    r_ecc = next(r for r in health_results if r.gpu_id == "gpu-ecc-fault")
    assert r_ecc.is_healthy is False
    assert r_ecc.status == GPUHealthStatus.ECC_ERROR
    assert "ecc" in r_ecc.reason.lower()

    # 3. Verify SQL persistence of health status
    db_dev_overheated = await manager.get_device("gpu-overheated")
    assert db_dev_overheated is not None
    assert db_dev_overheated.is_healthy is False
    assert db_dev_overheated.health_status == GPUHealthStatus.OVERHEATED

    db_dev_normal = await manager.get_device("gpu-normal")
    assert db_dev_normal is not None
    assert db_dev_normal.is_healthy is True
    assert db_dev_normal.health_status == GPUHealthStatus.HEALTHY

    # 4. Verify admission controller ignores unhealthy GPUs
    admission = await manager.check_memory_admission(
        required_bytes=1000000000,
        target_gpu_id="gpu-overheated"
    )
    assert admission["admitted"] is False
    assert "insufficient" in admission["reason"].lower() or "unhealthy" in admission["reason"].lower()
