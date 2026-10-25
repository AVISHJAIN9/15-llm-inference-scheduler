"""
API-Key Authentication (SCH-125).
Provides secure API key validation with SHA-256 hashing and tenant association.
"""

import hashlib
import secrets
from typing import Dict, Optional, List
from dataclasses import dataclass
from fastapi import Request, HTTPException, Security, status
from fastapi.security import APIKeyHeader, HTTPBearer, HTTPAuthorizationCredentials


@dataclass
class APIKeyRecord:
    key_id: str
    key_prefix: str
    hashed_key: str
    tenant_id: str
    roles: List[str]
    is_active: bool = True
    rate_limit_rpm: int = 60

APIKeyMetadata = APIKeyRecord



class APIKeyManager:
    """Manages creation, hashing, and authentication of API keys."""

    def __init__(self):
        # Maps hashed_key -> APIKeyRecord
        self._keys: Dict[str, APIKeyRecord] = {}

    @staticmethod
    def hash_key(raw_key: str) -> str:
        return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()

    def generate_api_key(
        self,
        tenant_id: str,
        roles: Optional[List[str]] = None,
        rate_limit_rpm: int = 60
    ) -> tuple[str, APIKeyRecord]:
        """Generates a new secure random API key and stores its hash."""
        random_suffix = secrets.token_urlsafe(32)
        raw_key = f"sk-sch-{tenant_id}-{random_suffix}"
        key_id = f"key-{secrets.token_hex(6)}"
        hashed = self.hash_key(raw_key)

        record = APIKeyRecord(
            key_id=key_id,
            key_prefix=raw_key[:10] + "...",
            hashed_key=hashed,
            tenant_id=tenant_id,
            roles=roles or ["inference"],
            is_active=True,
            rate_limit_rpm=rate_limit_rpm
        )
        self._keys[hashed] = record
        return raw_key, record

    def authenticate(self, raw_key: Optional[str]) -> Optional[APIKeyRecord]:
        """Validates raw key against stored hashes."""
        if not raw_key:
            return None
        hashed = self.hash_key(raw_key.strip())
        record = self._keys.get(hashed)
        if record and record.is_active:
            return record


        return None

    def revoke_key(self, raw_key: str) -> bool:
        hashed = self.hash_key(raw_key)
        if hashed in self._keys:
            self._keys[hashed].is_active = False
            return True
        return False


default_api_key_manager = APIKeyManager()
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
bearer_security = HTTPBearer(auto_error=False)


async def require_api_key(
    request: Request,
    header_key: Optional[str] = Security(api_key_header),
    bearer_creds: Optional[HTTPAuthorizationCredentials] = Security(bearer_security)
) -> APIKeyRecord:
    """FastAPI dependency for authenticating incoming API requests."""
    raw_key = header_key or (bearer_creds.credentials if bearer_creds else None)
    if not raw_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": {"code": "UNAUTHORIZED", "message": "Missing API key in Authorization or X-API-Key header"}}
        )

    record = default_api_key_manager.authenticate(raw_key)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": {"code": "INVALID_API_KEY", "message": "Invalid or revoked API key"}}
        )

    # Attach tenant info to request state
    request.state.tenant_id = record.tenant_id
    request.state.api_key_record = record
    return record
