import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from db.database import Base
from models.loading import ModelLoadingManager, ModelLoadStatus

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
async def test_SCH_033_model_loading(async_session):
    """
    SCH-033: Model loading (BE+DB).
    Coordinates model loading lifecycle on inference workers/accelerators,
    tracks asynchronous load transitions (LOADING -> LOADED / FAILED),
    and persists worker model residency in SQL store.
    """
    loader = ModelLoadingManager(async_session)

    # 1. Initiate loading a model onto worker-1
    inst = await loader.initiate_load(
        worker_id="worker-1",
        model_name="mistral-7b",
        gpu_id="gpu-0"
    )
    assert inst.instance_id.startswith("inst-")
    assert inst.worker_id == "worker-1"
    assert inst.model_name == "mistral-7b"
    assert inst.load_status == ModelLoadStatus.LOADING

    # Check that model is not yet considered loaded
    is_ready = await loader.is_model_loaded_on_worker("worker-1", "mistral-7b")
    assert is_ready is False

    # 2. Complete model load with resident memory footprint and duration
    completed = await loader.complete_load(
        instance_id=inst.instance_id,
        loaded_memory_bytes=14 * 1024 * 1024 * 1024,
        duration_seconds=4.2
    )
    assert completed.load_status == ModelLoadStatus.LOADED
    assert completed.loaded_memory_bytes == 14 * 1024 * 1024 * 1024
    assert completed.load_duration_seconds == 4.2

    # Verify query now shows model as ready
    is_ready_now = await loader.is_model_loaded_on_worker("worker-1", "mistral-7b")
    assert is_ready_now is True

    # 3. Initiate second load that fails (e.g. weights download timeout / OOM)
    inst_fail = await loader.initiate_load(
        worker_id="worker-2",
        model_name="huge-model-70b",
        gpu_id="gpu-1"
    )
    failed = await loader.fail_load(
        instance_id=inst_fail.instance_id,
        error_message="CUDA out of memory during weight allocation"
    )
    assert failed.load_status == ModelLoadStatus.FAILED
    assert "out of memory" in failed.error_message

    # 4. List all active loaded models on worker-1
    active_instances = await loader.get_worker_loaded_models("worker-1")
    assert len(active_instances) == 1
    assert active_instances[0].model_name == "mistral-7b"

    # 5. Unload model
    unloaded = await loader.unload_model(inst.instance_id)
    assert unloaded is True

    # Verify model is no longer active
    active_after = await loader.get_worker_loaded_models("worker-1")
    assert len(active_after) == 0
