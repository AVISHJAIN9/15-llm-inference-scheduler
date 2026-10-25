import pytest
import time
from security.auth import APIKeyManager
from security.isolation import TenantIsolationGuard, TenantIsolationError
from security.rate_limit import SlidingWindowRateLimiter
from scheduler.models import InferenceRequest
from scheduler.queue import FIFOQueue


def test_SCH_125_api_key_authentication():
    """
    SCH-125: API-key authentication (BE, P2).
    Verifies:
    - Secure random key generation with SHA-256 hash storage
    - Validation of valid raw keys returning tenant record
    - Rejection of invalid, spoofed, or revoked keys
    """
    manager = APIKeyManager()

    # 1. Generate key for tenant-alpha
    raw_key, record = manager.generate_api_key(tenant_id="tenant-alpha", roles=["inference", "admin"])
    assert raw_key.startswith("sk-sch-tenant-alpha-")
    assert record.tenant_id == "tenant-alpha"
    assert "admin" in record.roles
    assert record.hashed_key != raw_key  # Must not store plaintext key

    # 2. Authenticate with valid key
    auth_rec = manager.authenticate(raw_key)
    assert auth_rec is not None
    assert auth_rec.tenant_id == "tenant-alpha"
    assert auth_rec.is_active is True

    # 3. Authenticate with invalid key -> None
    assert manager.authenticate("sk-sch-invalid-token") is None
    assert manager.authenticate("") is None
    assert manager.authenticate(None) is None

    # 4. Revoke key and verify rejection
    assert manager.revoke_key(raw_key) is True
    assert manager.authenticate(raw_key) is None


def test_SCH_128_tenant_isolation():
    """
    SCH-128: Tenant isolation (BE, P2).
    Verifies (§9 Invariant):
    - Multi-tenant isolation barriers prevent cross-tenant request access
    - Tenant A cannot inspect or cancel Tenant B's queue items
    """
    queue = FIFOQueue(max_capacity=100)

    req_a1 = InferenceRequest(request_id="req-a1", model_name="llama-3", prompt="a1", tenant_id="tenant-a")
    req_a2 = InferenceRequest(request_id="req-a2", model_name="llama-3", prompt="a2", tenant_id="tenant-a")
    req_b1 = InferenceRequest(request_id="req-b1", model_name="llama-3", prompt="b1", tenant_id="tenant-b")

    queue.enqueue(req_a1)
    queue.enqueue(req_a2)
    queue.enqueue(req_b1)

    # 1. Tenant-scoped queue view
    a_queue = TenantIsolationGuard.filter_queue_by_tenant(queue, "tenant-a")
    assert len(a_queue) == 2
    assert all(r.tenant_id == "tenant-a" for r in a_queue)
    assert "req-b1" not in [r.request_id for r in a_queue]

    b_queue = TenantIsolationGuard.filter_queue_by_tenant(queue, "tenant-b")
    assert len(b_queue) == 1
    assert b_queue[0].request_id == "req-b1"

    # 2. Adversarial cancellation check: tenant-b attempts to cancel tenant-a's request
    with pytest.raises(TenantIsolationError) as exc_info:
        TenantIsolationGuard.cancel_tenant_request(queue, tenant_id="tenant-b", request_id="req-a1")
    assert "cannot access request" in str(exc_info.value)
    # Confirm req-a1 is STILL in queue
    assert queue.size() == 3

    # 3. Legitimate cancellation: tenant-a cancels their own request
    cancelled = TenantIsolationGuard.cancel_tenant_request(queue, tenant_id="tenant-a", request_id="req-a1")
    assert cancelled is not None
    assert cancelled.request_id == "req-a1"
    assert queue.size() == 2


def test_SCH_130_rate_limiting():
    """
    SCH-130: Rate limiting (BE, P2).
    Verifies:
    - Sliding window limit per tenant/key
    - Accurate remaining count tracking
    - Throttling with Retry-After calculation upon breach
    """
    limiter = SlidingWindowRateLimiter(default_limit=3, window_seconds=10.0)
    current_clock = 1000.0

    # 1. First 3 requests succeed
    ok1, rem1, retry1 = limiter.check_and_record("tenant-pro", now=current_clock)
    assert ok1 is True
    assert rem1 == 2
    assert retry1 == 0.0

    ok2, rem2, _ = limiter.check_and_record("tenant-pro", now=current_clock + 1.0)
    assert ok2 is True
    assert rem2 == 1

    ok3, rem3, _ = limiter.check_and_record("tenant-pro", now=current_clock + 2.0)
    assert ok3 is True
    assert rem3 == 0

    # 2. 4th request exceeds rate limit (capacity is 3 per 10s)
    ok4, rem4, retry4 = limiter.check_and_record("tenant-pro", now=current_clock + 3.0)
    assert ok4 is False
    assert rem4 == 0
    # Oldest timestamp was current_clock (1000.0). Window is 10s.
    # Expiration is at 1010.0. Current is 1003.0 -> retry_after is ~7.0s
    assert retry4 == 7.0

    # 3. Other tenant is unaffected (independent quota)
    ok_other, rem_other, _ = limiter.check_and_record("tenant-other", now=current_clock + 3.0)
    assert ok_other is True
    assert rem_other == 2

    # 4. Advance clock past the window for tenant-pro
    ok_after, rem_after, _ = limiter.check_and_record("tenant-pro", now=current_clock + 13.0)
    assert ok_after is True
    assert rem_after == 2
