import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from db.database import Base
from models.registry import ModelRegistry, ModelSchema
from models.footprint import ModelMemoryFootprintManager, MemoryFootprintCalculator, PrecisionBytes

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
async def test_SCH_038_model_memory_footprint(async_session):
    """
    SCH-038: Model memory footprint (BE+DB).
    Computes rigorous model memory footprint (weights bytes per quantization,
    activation overhead, workspace scratchpad, tensor parallelism distribution)
    and persists footprint profiles in SQL store.
    """
    calc = MemoryFootprintCalculator()

    # 1. Test precision byte scaling
    assert calc.get_bytes_per_param("fp32") == 4.0
    assert calc.get_bytes_per_param("fp16") == 2.0
    assert calc.get_bytes_per_param("bf16") == 2.0
    assert calc.get_bytes_per_param("int8") == 1.0
    assert calc.get_bytes_per_param("fp8") == 1.0
    assert calc.get_bytes_per_param("int4") == 0.5
    assert calc.get_bytes_per_param("awq") == 0.5

    # 2. Compute footprint for LLaMA 8B FP16 (TP=1)
    footprint_8b_fp16 = calc.compute_footprint(
        parameter_count=8_000_000_000,
        quantization="fp16",
        max_context_length=8192,
        hidden_size=4096,
        num_layers=32,
        tensor_parallel_size=1
    )
    # Weights = 8B * 2 = 16,000,000,000 bytes (~16 GB)
    assert footprint_8b_fp16.weight_memory_bytes == 16_000_000_000
    assert footprint_8b_fp16.activation_overhead_bytes > 0
    assert footprint_8b_fp16.total_required_bytes == (
        footprint_8b_fp16.weight_memory_bytes +
        footprint_8b_fp16.activation_overhead_bytes +
        footprint_8b_fp16.workspace_overhead_bytes
    )
    assert footprint_8b_fp16.per_gpu_memory_bytes == footprint_8b_fp16.total_required_bytes

    # 3. Compute footprint for LLaMA 70B INT4 with Tensor Parallelism = 4
    footprint_70b_tp4 = calc.compute_footprint(
        parameter_count=70_000_000_000,
        quantization="int4",
        max_context_length=4096,
        hidden_size=8192,
        num_layers=80,
        tensor_parallel_size=4
    )
    # Weights = 70B * 0.5 = 35,000,000,000 bytes
    assert footprint_70b_tp4.weight_memory_bytes == 35_000_000_000
    # Per-GPU weight allocation must be divided by TP=4
    expected_weight_per_gpu = 35_000_000_000 // 4
    assert footprint_70b_tp4.per_gpu_weight_bytes == expected_weight_per_gpu

    # 4. Persist footprint in SQL database via ModelMemoryFootprintManager
    manager = ModelMemoryFootprintManager(async_session)
    stored = await manager.store_footprint(
        model_name="llama-3-8b-instruct",
        footprint=footprint_8b_fp16
    )
    assert stored.model_name == "llama-3-8b-instruct"
    assert stored.weight_memory_bytes == 16_000_000_000

    # Retrieve from SQL and verify equality
    retrieved = await manager.get_footprint("llama-3-8b-instruct")
    assert retrieved is not None
    assert retrieved.model_name == "llama-3-8b-instruct"
    assert retrieved.total_required_bytes == footprint_8b_fp16.total_required_bytes
    assert retrieved.quantization == "fp16"

    # 5. Validation: negative parameter count or unsupported quantization raises error
    with pytest.raises(ValueError):
        calc.compute_footprint(parameter_count=-10, quantization="fp16")

    with pytest.raises(ValueError):
        calc.compute_footprint(parameter_count=1_000_000, quantization="unsupported_quant")
