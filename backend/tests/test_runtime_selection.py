import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from db.database import Base
from models.runtime import RuntimeSelector, RuntimeEngineConfig, RuntimeEngineType

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
async def test_SCH_042_runtime_selection(async_session):
    """
    SCH-042: Runtime selection (BE+DB).
    Manages and selects optimal execution runtimes (vLLM, TensorRT-LLM, TGI, ONNX)
    based on hardware accelerator capabilities, model architecture, and feature requirements.
    """
    selector = RuntimeSelector(async_session)

    # 1. Register multiple runtime configurations for LLaMA-3
    cfg_vllm = RuntimeEngineConfig(
        model_name="llama-3-8b",
        runtime_engine=RuntimeEngineType.VLLM,
        min_compute_capability=7.0,
        supports_chunked_prefill=True,
        supports_speculative_decoding=False,
        max_batch_tokens=8192,
        is_preferred=False
    )
    cfg_trt = RuntimeEngineConfig(
        model_name="llama-3-8b",
        runtime_engine=RuntimeEngineType.TENSORRT_LLM,
        min_compute_capability=8.0,  # Requires Ampere or newer
        supports_chunked_prefill=True,
        supports_speculative_decoding=True,
        max_batch_tokens=16384,
        is_preferred=True
    )
    cfg_onnx = RuntimeEngineConfig(
        model_name="llama-3-8b",
        runtime_engine=RuntimeEngineType.ONNX_RUNTIME,
        min_compute_capability=6.0,
        supports_chunked_prefill=False,
        supports_speculative_decoding=False,
        max_batch_tokens=2048,
        is_preferred=False
    )

    await selector.register_runtime_config(cfg_vllm)
    await selector.register_runtime_config(cfg_trt)
    await selector.register_runtime_config(cfg_onnx)

    # 2. Selection on modern GPU (compute cap 9.0 - Hopper):
    # Both vLLM and TRT-LLM are compatible; TRT-LLM is preferred and supports speculative decoding
    selected_hopper = await selector.select_optimal_runtime(
        model_name="llama-3-8b",
        gpu_compute_capability=9.0,
        require_speculative_decoding=True
    )
    assert selected_hopper is not None
    assert selected_hopper.runtime_engine == RuntimeEngineType.TENSORRT_LLM

    # 3. Selection on older GPU (compute cap 7.5 - Turing):
    # TRT-LLM requires 8.0 -> disqualified. vLLM (min 7.0) should be selected!
    selected_turing = await selector.select_optimal_runtime(
        model_name="llama-3-8b",
        gpu_compute_capability=7.5,
        require_speculative_decoding=False
    )
    assert selected_turing is not None
    assert selected_turing.runtime_engine == RuntimeEngineType.VLLM

    # 4. Incompatible requirements: speculative decoding on Turing (where TRT is disqualified and vLLM doesn't support it)
    selected_incompatible = await selector.select_optimal_runtime(
        model_name="llama-3-8b",
        gpu_compute_capability=7.5,
        require_speculative_decoding=True
    )
    assert selected_incompatible is None

    # 5. List configs from database
    configs = await selector.list_runtime_configs("llama-3-8b")
    assert len(configs) == 3
