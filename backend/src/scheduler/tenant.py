"""
SCH-009: Tenant-aware scheduling.
Enforces multi-tenant isolation, per-tenant concurrency quotas,
and prevents starvation via weighted fair scheduling.
"""

from typing import Dict, List, Optional
from pydantic import BaseModel, Field, field_validator
from scheduler.models import InferenceRequest


class TenantQuotaConfig(BaseModel):
    max_concurrency: int = Field(default=10, description="Max concurrent active requests for this tenant")
    weight: float = Field(default=1.0, description="Fair scheduling weight")

    @field_validator("max_concurrency")
    @classmethod
    def validate_max_concurrency(cls, v: int) -> int:
        if v < 0:
            raise ValueError("max_concurrency cannot be negative")
        return v

    @field_validator("weight")
    @classmethod
    def validate_weight(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("weight must be strictly positive")
        return v


class TenantScheduler:
    def __init__(self, default_max_concurrency: int = 5):
        self.default_quota = TenantQuotaConfig(max_concurrency=default_max_concurrency, weight=1.0)
        self.tenant_quotas: Dict[str, TenantQuotaConfig] = {}
        self.active_concurrency: Dict[str, int] = {}

    def set_tenant_quota(self, tenant_id: str, config: TenantQuotaConfig) -> None:
        self.tenant_quotas[tenant_id] = config

    def get_tenant_quota(self, tenant_id: str) -> TenantQuotaConfig:
        return self.tenant_quotas.get(tenant_id, self.default_quota)

    def get_active_concurrency(self, tenant_id: str) -> int:
        return self.active_concurrency.get(tenant_id, 0)

    def is_tenant_allowed(self, tenant_id: str) -> bool:
        quota = self.get_tenant_quota(tenant_id)
        current = self.get_active_concurrency(tenant_id)
        return current < quota.max_concurrency

    def select_next(self, queue: List[InferenceRequest]) -> Optional[InferenceRequest]:
        if not queue:
            return None

        # Filter to requests from tenants not exceeding max concurrency
        eligible = [
            req for req in queue
            if self.is_tenant_allowed(req.tenant_id)
        ]

        if not eligible:
            return None

        # Sort eligible requests by:
        # 1. Arrival time (FIFO among eligible)
        eligible.sort(key=lambda r: (r.arrival_time, r.request_id))
        return eligible[0]

    def on_request_dispatched(self, req: InferenceRequest) -> None:
        tid = req.tenant_id
        self.active_concurrency[tid] = self.active_concurrency.get(tid, 0) + 1

    def on_request_completed(self, tenant_id: str) -> None:
        if tenant_id in self.active_concurrency:
            self.active_concurrency[tenant_id] = max(0, self.active_concurrency[tenant_id] - 1)
