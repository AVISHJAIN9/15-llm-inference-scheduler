"""
Tenant KV Cache Quota and Isolation Manager (SCH-055).
Enforces strict multi-tenant cache quotas (Invariant P15 §9):
- Quotas are strictly enforced and never exceeded.
- Tenant isolation prevents one tenant from evicting another's blocks.
- Persists quota configurations and allocation state in SQL store.
"""

import math
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List, Set
from sqlalchemy import Column, String, Integer, DateTime, select
from sqlalchemy.ext.asyncio import AsyncSession
from db.database import Base
from kv.allocator import PagedKVCacheManager


class TenantQuotaExceededError(Exception):
    """Raised when an allocation would cause a tenant to exceed their configured cache quota."""
    pass


class TenantCacheQuotaRecord(Base):
    __tablename__ = "tenant_cache_quotas"

    tenant_id = Column(String(64), primary_key=True)
    max_quota_blocks = Column(Integer, nullable=False)
    allocated_blocks = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tenant_id": self.tenant_id,
            "max_quota_blocks": self.max_quota_blocks,
            "allocated_blocks": self.allocated_blocks,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class TenantCacheQuotaManager:
    def __init__(self, session: AsyncSession, cache_manager: Optional[PagedKVCacheManager] = None):
        self.session = session
        self.cache_mgr = cache_manager or PagedKVCacheManager()
        # Tenant isolation state tracking: sequence -> tenant, and tenant -> set of allocated block IDs
        self.sequence_tenants: Dict[str, str] = {}
        self.tenant_blocks: Dict[str, Set[int]] = {}

    async def set_tenant_quota(self, tenant_id: str, max_quota_blocks: int) -> TenantCacheQuotaRecord:
        """Sets or updates the maximum KV-cache block quota for a tenant in SQL store (SCH-055)."""
        if max_quota_blocks <= 0:
            raise ValueError("max_quota_blocks must be positive")

        stmt = select(TenantCacheQuotaRecord).where(TenantCacheQuotaRecord.tenant_id == tenant_id)
        res = await self.session.execute(stmt)
        record = res.scalar_one_or_none()

        now = datetime.now(timezone.utc)
        if record:
            record.max_quota_blocks = max_quota_blocks
            record.updated_at = now
        else:
            record = TenantCacheQuotaRecord(
                tenant_id=tenant_id,
                max_quota_blocks=max_quota_blocks,
                allocated_blocks=0,
                created_at=now,
                updated_at=now
            )
            self.session.add(record)

        await self.session.commit()
        return record

    async def get_tenant_quota(self, tenant_id: str) -> Optional[TenantCacheQuotaRecord]:
        """Queries the current quota and allocation for a tenant from SQL store (SCH-055)."""
        stmt = select(TenantCacheQuotaRecord).where(TenantCacheQuotaRecord.tenant_id == tenant_id)
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def allocate_for_tenant(
        self,
        tenant_id: str,
        sequence_id: str,
        num_tokens: int
    ) -> List[int]:
        """
        Allocates blocks for a sequence strictly bounded by the tenant's cache quota (SCH-055).
        Quota is NEVER exceeded.
        """
        record = await self.get_tenant_quota(tenant_id)
        if not record:
            raise ValueError(f"No quota configured for tenant '{tenant_id}'")

        blocks_needed = max(1, math.ceil(num_tokens / self.cache_mgr.block_size))
        if record.allocated_blocks + blocks_needed > record.max_quota_blocks:
            raise TenantQuotaExceededError(
                f"Requested {blocks_needed} blocks exceeds tenant cache quota "
                f"({record.allocated_blocks}/{record.max_quota_blocks} allocated)"
            )

        allocated = self.cache_mgr.allocate(sequence_id=sequence_id, num_tokens=num_tokens)
        if allocated is None:
            raise MemoryError("Insufficient physical blocks in cache manager")

        # Track tenant ownership for cross-tenant isolation
        self.sequence_tenants[sequence_id] = tenant_id
        t_blocks = self.tenant_blocks.setdefault(tenant_id, set())
        t_blocks.update(allocated)

        record.allocated_blocks += len(allocated)
        record.updated_at = datetime.now(timezone.utc)
        await self.session.commit()
        return allocated

    async def evict_tenant_blocks(self, tenant_id: str, num_blocks: int) -> int:
        """
        Evicts unreferenced blocks belonging SOLELY to tenant_id (SCH-055).
        Invariant: One tenant CANNOT evict another's blocks beyond its quota.
        """
        t_blocks = self.tenant_blocks.get(tenant_id, set())
        evictable = [b_id for b_id in t_blocks if self.cache_mgr.blocks[b_id].ref_count == 0]
        to_evict = evictable[:num_blocks]

        for b_id in to_evict:
            t_blocks.remove(b_id)
            if b_id not in self.cache_mgr.free_blocks:
                self.cache_mgr.free_blocks.append(b_id)

        record = await self.get_tenant_quota(tenant_id)
        if record and to_evict:
            record.allocated_blocks = max(0, record.allocated_blocks - len(to_evict))
            record.updated_at = datetime.now(timezone.utc)
            await self.session.commit()

        return len(to_evict)

    async def release_tenant_sequence(self, tenant_id: str, sequence_id: str) -> bool:
        """Frees sequence allocations and updates tenant allocation state in SQL (SCH-055)."""
        if sequence_id not in self.sequence_tenants:
            return False

        owner = self.sequence_tenants.pop(sequence_id)
        if owner != tenant_id:
            return False

        table = self.cache_mgr.block_tables.get(sequence_id, [])
        num_freed = len(table)
        t_blocks = self.tenant_blocks.get(tenant_id, set())
        for b_id in table:
            t_blocks.discard(b_id)

        self.cache_mgr.free(sequence_id)

        record = await self.get_tenant_quota(tenant_id)
        if record:
            record.allocated_blocks = max(0, record.allocated_blocks - num_freed)
            record.updated_at = datetime.now(timezone.utc)
            await self.session.commit()

        return True
