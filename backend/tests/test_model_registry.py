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
async def test_SCH_029_model_registry(async_session):
    registry = ModelRegistry(async_session)

    # Register model
    schema = ModelSchema(
        model_name="qwen2.5-0.5b",
        architecture="qwen2",
        max_context_length=32768,
        required_memory_bytes=1073741824,
        weights_uri="hf://Qwen/Qwen2.5-0.5B",
        is_active=True
    )
    saved = await registry.register_model(schema)
    assert saved.model_name == "qwen2.5-0.5b"
    assert saved.max_context_length == 32768

    # Query model
    fetched = await registry.get_model("qwen2.5-0.5b")
    assert fetched is not None
    assert fetched.architecture == "qwen2"
    assert fetched.required_memory_bytes == 1073741824

    # List active models
    models = await registry.list_active_models()
    assert len(models) == 1
    assert models[0].model_name == "qwen2.5-0.5b"

    # Invalid context length raises ValueError
    with pytest.raises(ValueError):
        await registry.register_model(ModelSchema(
            model_name="bad-model",
            architecture="test",
            max_context_length=0,
            required_memory_bytes=1000,
            weights_uri="hf://bad"
        ))
