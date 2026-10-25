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
async def test_SCH_020_device_assignment(async_session):
    """
    SCH-020: Device assignment (BE+DB).
    Assigns inference workloads to healthy GPUs based on memory budget and utilization policy,
    atomically reserves capacity in SQL store, and supports lifecycle release.
    """
    sim_devices = [
        {
            "gpu_id": "gpu-0",
            "device_name": "NVIDIA A100",
            "total_memory_bytes": 40 * 1024 * 1024 * 1024,  # 40 GB
            "allocated_memory_bytes": 10 * 1024 * 1024 * 1024,
            "utilization_pct": 75.0,  # High utilization
            "temperature_c": 50.0,
            "is_healthy": True
        },
        {
            "gpu_id": "gpu-1",
            "device_name": "NVIDIA A100",
            "total_memory_bytes": 40 * 1024 * 1024 * 1024,  # 40 GB
            "allocated_memory_bytes": 10 * 1024 * 1024 * 1024,
            "utilization_pct": 25.0,  # Low utilization
            "temperature_c": 48.0,
            "is_healthy": True
        },
        {
            "gpu_id": "gpu-unhealthy",
            "device_name": "NVIDIA A100",
            "total_memory_bytes": 40 * 1024 * 1024 * 1024,
            "allocated_memory_bytes": 0,
            "utilization_pct": 5.0,
            "temperature_c": 95.0,
            "is_healthy": False  # Unhealthy device must never be assigned
        }
    ]
    telemetry = NVMLTelemetryAdapter(simulated_devices=sim_devices)
    manager = GPUManager(async_session, telemetry_adapter=telemetry)
    await manager.sync_inventory(node_id="node-1")

    # 1. Assign workload with least_utilized policy -> should pick gpu-1 (utilization 25.0% vs 75.0%)
    req_mem = 4 * 1024 * 1024 * 1024  # 4 GB
    assignment1 = await manager.assign_device(
        request_id="req-101",
        required_memory_bytes=req_mem,
        policy="least_utilized"
    )
    assert assignment1 is not None
    assert assignment1["gpu_id"] == "gpu-1"
    assert assignment1["request_id"] == "req-101"
    assert assignment1["allocated_memory_bytes"] == req_mem

    # Verify SQL state updated: gpu-1 allocated memory increased
    dev1 = await manager.get_device("gpu-1")
    assert dev1.allocated_memory_bytes == 14 * 1024 * 1024 * 1024

    # 2. Target specific healthy GPU (gpu-0)
    assignment2 = await manager.assign_device(
        request_id="req-102",
        required_memory_bytes=req_mem,
        target_gpu_id="gpu-0"
    )
    assert assignment2 is not None
    assert assignment2["gpu_id"] == "gpu-0"

    # 3. Attempt to assign to unhealthy GPU -> must be rejected
    assignment_bad = await manager.assign_device(
        request_id="req-103",
        required_memory_bytes=req_mem,
        target_gpu_id="gpu-unhealthy"
    )
    assert assignment_bad is None

    # 4. Attempt to assign exceeding capacity -> must return None
    assignment_oom = await manager.assign_device(
        request_id="req-104",
        required_memory_bytes=100 * 1024 * 1024 * 1024  # 100 GB exceeds all devices
    )
    assert assignment_oom is None

    # 5. Release assignment and verify capacity restored in SQL
    released = await manager.release_device_assignment(assignment1["assignment_id"])
    assert released is True

    dev1_after = await manager.get_device("gpu-1")
    assert dev1_after.allocated_memory_bytes == 10 * 1024 * 1024 * 1024

    # Re-releasing the same assignment returns False (idempotent guard)
    re_release = await manager.release_device_assignment(assignment1["assignment_id"])
    assert re_release is False
