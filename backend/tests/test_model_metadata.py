import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from db.database import Base
from models.registry import ModelRegistry, ModelSchema

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
async def test_SCH_030_model_metadata(async_session):
    """
    SCH-030: Model metadata (BE+DB).
    Stores, validates, and manages detailed model architectural parameters
    (parameters count, quantization type, layer/head dimensions, tensor parallelism) in SQL store.
    """
    registry = ModelRegistry(async_session)

    # 1. Register model with full architectural metadata
    model_meta = ModelSchema(
        model_name="llama-3-8b-instruct",
        architecture="llama",
        max_context_length=8192,
        required_memory_bytes=16 * 1024 * 1024 * 1024,
        weights_uri="hf://meta-llama/Meta-Llama-3-8B-Instruct",
        parameter_count=8_030_000_000,
        quantization="bf16",
        num_layers=32,
        num_heads=32,
        num_kv_heads=8,
        hidden_size=4096,
        vocab_size=128256,
        tensor_parallel_size=1,
        is_active=True
    )
    saved = await registry.register_model(model_meta)
    assert saved.model_name == "llama-3-8b-instruct"
    assert saved.parameter_count == 8_030_000_000
    assert saved.quantization == "bf16"
    assert saved.num_kv_heads == 8
    assert saved.tensor_parallel_size == 1

    # 2. Query model and verify persistence of all metadata fields
    fetched = await registry.get_model("llama-3-8b-instruct")
    assert fetched is not None
    assert fetched.parameter_count == 8_030_000_000
    assert fetched.quantization == "bf16"
    assert fetched.num_layers == 32
    assert fetched.num_heads == 32
    assert fetched.num_kv_heads == 8
    assert fetched.hidden_size == 4096
    assert fetched.vocab_size == 128256
    assert fetched.tensor_parallel_size == 1

    # 3. Validation: parameter_count must be positive if specified
    with pytest.raises(ValueError, match="parameter_count"):
        await registry.register_model(ModelSchema(
            model_name="bad-meta-model",
            architecture="llama",
            max_context_length=4096,
            required_memory_bytes=1000,
            weights_uri="hf://test",
            parameter_count=-100
        ))

    # 4. Validation: quantization must be supported format
    with pytest.raises(ValueError, match="quantization"):
        await registry.register_model(ModelSchema(
            model_name="bad-quant-model",
            architecture="llama",
            max_context_length=4096,
            required_memory_bytes=1000,
            weights_uri="hf://test",
            quantization="invalid_format"
        ))
