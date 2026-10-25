import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from db.database import Base
from kv.allocator import PagedKVCacheManager
from kv.quota import TenantCacheQuotaManager, TenantQuotaExceededError

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
async def test_SCH_055_tenant_cache_quotas(async_session):
    """
    SCH-055: Tenant cache quotas (BE+DB).
    Enforces strict tenant KV cache quotas (Invariant P15 §9):
    - Tenant cache quotas are NEVER exceeded.
    - One tenant CANNOT evict another tenant's blocks beyond its quota.
    - Quota state persisted in SQL store.
    """
    cache_mgr = PagedKVCacheManager(total_blocks=100, block_size=16)
    quota_mgr = TenantCacheQuotaManager(async_session, cache_manager=cache_mgr)

    # 1. Configure quotas: Tenant A has 10 blocks (160 tokens), Tenant B has 20 blocks (320 tokens)
    await quota_mgr.set_tenant_quota(tenant_id="tenant-a", max_quota_blocks=10)
    await quota_mgr.set_tenant_quota(tenant_id="tenant-b", max_quota_blocks=20)

    # 2. Allocate 8 blocks for Tenant A (within quota of 10)
    alloc_a = await quota_mgr.allocate_for_tenant(
        tenant_id="tenant-a",
        sequence_id="seq-a1",
        num_tokens=128  # 8 blocks
    )
    assert len(alloc_a) == 8
    q_a = await quota_mgr.get_tenant_quota("tenant-a")
    assert q_a.allocated_blocks == 8

    # 3. Attempt to allocate 4 more blocks for Tenant A (8 + 4 = 12 > 10)
    # Must reject with TenantQuotaExceededError, quota is NEVER exceeded!
    with pytest.raises(TenantQuotaExceededError, match="exceeds tenant cache quota"):
        await quota_mgr.allocate_for_tenant(
            tenant_id="tenant-a",
            sequence_id="seq-a2",
            num_tokens=64  # 4 blocks
        )

    # Verify Tenant A allocation stayed at 8, never exceeded
    q_a_after = await quota_mgr.get_tenant_quota("tenant-a")
    assert q_a_after.allocated_blocks == 8

    # 4. Cross-tenant isolation invariant:
    # Tenant B allocates 15 blocks (within its quota of 20)
    alloc_b = await quota_mgr.allocate_for_tenant(
        tenant_id="tenant-b",
        sequence_id="seq-b1",
        num_tokens=240  # 15 blocks
    )
    assert len(alloc_b) == 15
    q_b = await quota_mgr.get_tenant_quota("tenant-b")
    assert q_b.allocated_blocks == 15

    # 5. Eviction test: Tenant B cannot evict Tenant A's blocks!
    # Even when attempting eviction under tenant-b context, tenant-a's blocks are strictly protected.
    evicted_by_b = await quota_mgr.evict_tenant_blocks(tenant_id="tenant-b", num_blocks=5)
    # Only Tenant B's own unreferenced blocks can be touched, Tenant A's allocation unchanged
    q_a_final = await quota_mgr.get_tenant_quota("tenant-a")
    assert q_a_final.allocated_blocks == 8

    # 6. Release Tenant A sequence and verify recovery in SQL
    released = await quota_mgr.release_tenant_sequence(tenant_id="tenant-a", sequence_id="seq-a1")
    assert released is True
    q_a_released = await quota_mgr.get_tenant_quota("tenant-a")
    assert q_a_released.allocated_blocks == 0
