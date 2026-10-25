"""
Data models for LLM Inference Scheduler: requests, admission policies, and states.
"""

from enum import Enum
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field

class RequestStatus(str, Enum):
    PENDING = "PENDING"
    ADMITTED = "ADMITTED"
    QUEUED = "QUEUED"
    IN_FLIGHT = "IN_FLIGHT"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"

class InferenceRequest(BaseModel):
    request_id: str
    model_name: str
    prompt: str
    max_tokens: int = 128
    priority: int = 0
    tenant_id: str = "default"
    weight: float = 1.0
    arrival_time: float = 0.0
    effective_priority: float = 0.0
    deadline: Optional[float] = None
    status: RequestStatus = RequestStatus.PENDING
    tokens_generated: int = 0
    metadata: Dict[str, Any] = Field(default_factory=dict)
    assigned_worker_id: Optional[str] = None
    error_message: Optional[str] = None

class AdmissionDecision(BaseModel):
    admitted: bool
    reason: Optional[str] = None
    retryable: bool = False
    reason_code: Optional[str] = None
    request: Optional[InferenceRequest] = None
