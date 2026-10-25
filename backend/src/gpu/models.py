"""
GPU Device models and database schema (SCH-015, SCH-016, SCH-017).
"""

from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import Column, String, Integer, BigInteger, Float, Boolean, DateTime
from pydantic import BaseModel, ConfigDict
from db.database import Base

class GPUDeviceRecord(Base):
    __tablename__ = "gpu_devices"

    gpu_id = Column(String(64), primary_key=True, index=True)
    node_id = Column(String(64), nullable=False, index=True)
    device_name = Column(String(128), nullable=False)
    total_memory_bytes = Column(BigInteger, nullable=False)
    allocated_memory_bytes = Column(BigInteger, default=0, nullable=False)
    utilization_pct = Column(Float, default=0.0, nullable=False)
    temperature_c = Column(Float, default=0.0, nullable=False)
    is_healthy = Column(Boolean, default=True, nullable=False)
    health_status = Column(String(32), default="HEALTHY", nullable=False)
    health_reason = Column(String(256), nullable=True)
    last_health_check_at = Column(DateTime(timezone=True), nullable=True)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    def to_dict(self):
        return {
            "gpu_id": self.gpu_id,
            "node_id": self.node_id,
            "device_name": self.device_name,
            "total_memory_bytes": self.total_memory_bytes,
            "allocated_memory_bytes": self.allocated_memory_bytes,
            "free_memory_bytes": self.total_memory_bytes - self.allocated_memory_bytes,
            "utilization_pct": self.utilization_pct,
            "temperature_c": self.temperature_c,
            "is_healthy": self.is_healthy,
            "health_status": self.health_status,
            "health_reason": self.health_reason,
            "last_health_check_at": self.last_health_check_at.isoformat() if self.last_health_check_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None
        }

class GPUDeviceSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    gpu_id: str
    node_id: str
    device_name: str
    total_memory_bytes: int
    allocated_memory_bytes: int = 0
    utilization_pct: float = 0.0
    temperature_c: float = 0.0
    is_healthy: bool = True
    health_status: str = "HEALTHY"
    health_reason: Optional[str] = None
    last_health_check_at: Optional[datetime] = None

    @property
    def free_memory_bytes(self) -> int:
        return self.total_memory_bytes - self.allocated_memory_bytes

class GPUUtilizationRecord(Base):
    __tablename__ = "gpu_utilization_metrics"

    id = Column(Integer, primary_key=True, autoincrement=True)
    gpu_id = Column(String(64), nullable=False, index=True)
    compute_util_pct = Column(Float, nullable=False)
    memory_util_pct = Column(Float, nullable=False)
    temperature_c = Column(Float, default=0.0, nullable=False)
    timestamp = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False, index=True)

    def to_dict(self):
        return {
            "id": self.id,
            "gpu_id": self.gpu_id,
            "compute_util_pct": self.compute_util_pct,
            "memory_util_pct": self.memory_util_pct,
            "temperature_c": self.temperature_c,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None
        }

class GPUDeviceAssignmentRecord(Base):
    __tablename__ = "gpu_device_assignments"

    assignment_id = Column(String(64), primary_key=True)
    gpu_id = Column(String(64), nullable=False, index=True)
    request_id = Column(String(64), nullable=False, index=True)
    allocated_memory_bytes = Column(BigInteger, nullable=False)
    status = Column(String(32), default="ASSIGNED", nullable=False)
    assigned_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    released_at = Column(DateTime(timezone=True), nullable=True)

    def to_dict(self):
        return {
            "assignment_id": self.assignment_id,
            "gpu_id": self.gpu_id,
            "request_id": self.request_id,
            "allocated_memory_bytes": self.allocated_memory_bytes,
            "status": self.status,
            "assigned_at": self.assigned_at.isoformat() if self.assigned_at else None,
            "released_at": self.released_at.isoformat() if self.released_at else None
        }


