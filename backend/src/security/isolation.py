"""
Tenant Isolation Guard (SCH-128).
Guarantees complete multi-tenant request, queue, and resource isolation.
"""

from typing import List, Optional, Dict, Any
from scheduler.models import InferenceRequest
from scheduler.queue import FIFOQueue


class TenantIsolationError(Exception):
    """Raised when an operation attempts unauthorized cross-tenant resource access."""
    pass


class TenantIsolationGuard:
    """Enforces strict isolation barriers between tenants."""

    @staticmethod
    def assert_request_access(request_tenant_id: str, target_request: InferenceRequest) -> None:
        """
        Ensures tenant A cannot read, modify, or cancel tenant B's request.
        Adversarial check (§9 invariant).
        """
        if request_tenant_id != target_request.tenant_id:
            raise TenantIsolationError(
                f"Tenant '{request_tenant_id}' cannot access request '{target_request.request_id}' "
                f"belonging to tenant '{target_request.tenant_id}'"
            )

    @staticmethod
    def filter_queue_by_tenant(
        queue: FIFOQueue,
        tenant_id: str
    ) -> List[InferenceRequest]:
        """Returns only requests belonging to the authenticated tenant."""
        all_reqs = queue.all_requests()
        return [r for r in all_reqs if r.tenant_id == tenant_id]

    @staticmethod
    def cancel_tenant_request(
        queue: FIFOQueue,
        tenant_id: str,
        request_id: str
    ) -> Optional[InferenceRequest]:
        """Safely cancels a request only if it belongs to the requesting tenant."""
        all_reqs = queue.all_requests()
        target = next((r for r in all_reqs if r.request_id == request_id), None)
        if not target:
            return None

        TenantIsolationGuard.assert_request_access(tenant_id, target)
        return queue.remove(request_id)
