import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from db.database import Base
from kv.allocator import PagedKVCacheManager
from kv.budget import RequestCacheBudgetManager, BudgetExceededError

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
async def test_SCH_054_per_request_cache_budget(async_session):
    """
    SCH-054: Per-request cache budget (BE+DB).
    Enforces strict upper bounds on memory blocks per request.
    Budget breach rejects/queues, never over-commits (Invariant P15 §9).
    Persists budget allocations and breaches in SQL store.
    """
    cache_mgr = PagedKVCacheManager(total_blocks=100, block_size=16)
    budget_mgr = RequestCacheBudgetManager(async_session, cache_manager=cache_mgr)

    # 1. Register budget for request (max 4 blocks = 64 tokens)
    budget = await budget_mgr.set_request_budget(request_id="req-1", max_budget_blocks=4)
    assert budget.request_id == "req-1"
    assert budget.max_budget_blocks == 4
    assert budget.allocated_blocks == 0

    # 2. Allocate within budget (2 blocks = 32 tokens)
    allocated1 = await budget_mgr.allocate_within_budget(request_id="req-1", num_tokens=32)
    assert len(allocated1) == 2
    b_updated = await budget_mgr.get_request_budget("req-1")
    assert b_updated.allocated_blocks == 2

    # 3. Allocate remaining allowed budget (2 more blocks = 32 tokens -> 4 total)
    allocated2 = await budget_mgr.allocate_additional_blocks(request_id="req-1", num_additional_blocks=2)
    assert len(allocated2) == 2
    b_full = await budget_mgr.get_request_budget("req-1")
    assert b_full.allocated_blocks == 4

    # 4. Attempt to exceed request budget -> must reject with BudgetExceededError, NEVER over-commit!
    with pytest.raises(BudgetExceededError, match="exceeds per-request budget"):
        await budget_mgr.allocate_additional_blocks(request_id="req-1", num_additional_blocks=1)

    # Verify no over-commitment occurred in cache or SQL store
    b_after = await budget_mgr.get_request_budget("req-1")
    assert b_after.allocated_blocks == 4
    assert b_after.is_breached is True

    # 5. Release request budget and verify SQL state
    released = await budget_mgr.release_request("req-1")
    assert released is True
    b_released = await budget_mgr.get_request_budget("req-1")
    assert b_released.allocated_blocks == 0
    assert b_released.status == "RELEASED"
