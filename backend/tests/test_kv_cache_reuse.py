import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from db.database import Base
from kv.allocator import PagedKVCacheManager
from kv.reuse import KVCacheReuseManager

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
async def test_SCH_047_kv_cache_reuse(async_session):
    """
    SCH-047: KV-cache reuse (BE+DB).
    Identifies shared prompt prefixes, reuses pre-computed KV-cache memory blocks,
    increments block reference counts to prevent premature eviction, and records
    reuse telemetry and compute savings in SQL store.
    """
    cache_mgr = PagedKVCacheManager(total_blocks=100, block_size=16)
    reuse_mgr = KVCacheReuseManager(async_session, cache_manager=cache_mgr)

    shared_system_prompt = "You are a helpful coding assistant specialized in high-performance distributed systems."

    # 1. First request arrives: no cached prefix exists yet
    res1 = await reuse_mgr.allocate_with_reuse(
        request_id="req-1",
        tenant_id="tenant-a",
        prefix_text=shared_system_prompt,
        total_tokens=64  # 4 blocks of 16 tokens
    )
    assert res1.reused_blocks_count == 0
    assert res1.reused_tokens_count == 0
    assert res1.saved_computation_pct == 0.0
    assert len(res1.allocated_blocks) == 4

    # The prefix is now cached into the manager
    assert len(cache_mgr.prefix_cache) > 0

    # 2. Second request arrives with identical system prompt prefix
    res2 = await reuse_mgr.allocate_with_reuse(
        request_id="req-2",
        tenant_id="tenant-a",
        prefix_text=shared_system_prompt,
        total_tokens=64
    )
    assert res2.reused_blocks_count >= 1
    assert res2.reused_tokens_count >= 16
    assert res2.saved_computation_pct > 0.0

    # The shared prefix block's ref_count must be 2 (shared by req-1 and req-2)
    shared_block_id = res2.allocated_blocks[0]
    assert cache_mgr.blocks[shared_block_id].ref_count >= 2

    # 3. Retrieve reuse record from SQL database and verify persistence
    record = await reuse_mgr.get_reuse_record(res2.reuse_id)
    assert record is not None
    assert record.request_id == "req-2"
    assert record.tenant_id == "tenant-a"
    assert record.reused_blocks_count == res2.reused_blocks_count
    assert record.saved_computation_pct == res2.saved_computation_pct

    # 4. Aggregated reuse metrics for tenant
    metrics = await reuse_mgr.get_reuse_metrics(tenant_id="tenant-a")
    assert metrics["total_reuse_events"] == 1
    assert metrics["total_saved_blocks"] == res2.reused_blocks_count
    assert metrics["avg_saved_computation_pct"] > 0.0
