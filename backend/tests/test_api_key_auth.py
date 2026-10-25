import pytest
from security.auth import APIKeyManager, APIKeyRecord

def test_SCH_125_api_key_authentication():
    """
    SCH-125: API-key authentication (BE, P2).
    Validates secure API key generation with SHA-256 hashing, tenant association,
    active token verification, and revocation.
    """
    manager = APIKeyManager()

    # 1. Generate keys for distinct tenants
    raw_key1, rec1 = manager.generate_api_key(tenant_id="tenant-alpha", roles=["admin"])
    raw_key2, rec2 = manager.generate_api_key(tenant_id="tenant-beta", roles=["inference"])

    assert raw_key1.startswith("sk-sch-tenant-alpha-")
    assert rec1.tenant_id == "tenant-alpha"
    assert "admin" in rec1.roles
    assert rec1.is_active is True

    # 2. Authenticate with valid raw keys
    auth_rec1 = manager.authenticate(raw_key1)
    assert auth_rec1 is not None
    assert auth_rec1.tenant_id == "tenant-alpha"

    auth_rec2 = manager.authenticate(raw_key2)
    assert auth_rec2 is not None
    assert auth_rec2.tenant_id == "tenant-beta"

    # 3. Authenticate with missing or invalid keys -> returns None
    assert manager.authenticate(None) is None
    assert manager.authenticate("") is None
    assert manager.authenticate("sk-non-existent-fake-key") is None

    # 4. Revocation: revoking key1 prevents subsequent authentication
    assert manager.revoke_key(raw_key1) is True
    assert manager.authenticate(raw_key1) is None

    # Key 2 remains valid
    assert manager.authenticate(raw_key2) is not None
