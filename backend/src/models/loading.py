"""
Worker Model Loading Lifecycle Manager (SCH-033).
Tracks and coordinates model residency on inference workers and accelerators in SQL store.
"""

import uuid
from enum import Enum
from datetime import datetime, timezone
from typing import List, Optional
from sqlalchemy import Column, String, BigInteger, Float, DateTime, select
from sqlalchemy.ext.asyncio import AsyncSession
from db.database import Base


class ModelLoadStatus(str, Enum):
    LOADING = "LOADING"
    LOADED = "LOADED"
    FAILED = "FAILED"
    UNLOADING = "UNLOADING"
    UNLOADED = "UNLOADED"


class WorkerModelInstanceRecord(Base):
    __tablename__ = "worker_model_instances"

    instance_id = Column(String(64), primary_key=True)
    worker_id = Column(String(64), nullable=False, index=True)
    model_name = Column(String(128), nullable=False, index=True)
    gpu_id = Column(String(64), nullable=True)
    load_status = Column(String(32), default=ModelLoadStatus.LOADING.value, nullable=False)
    loaded_memory_bytes = Column(BigInteger, default=0, nullable=False)
    load_duration_seconds = Column(Float, default=0.0, nullable=False)
    error_message = Column(String(512), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    def to_dict(self):
        return {
            "instance_id": self.instance_id,
            "worker_id": self.worker_id,
            "model_name": self.model_name,
            "gpu_id": self.gpu_id,
            "load_status": self.load_status,
            "loaded_memory_bytes": self.loaded_memory_bytes,
            "load_duration_seconds": self.load_duration_seconds,
            "error_message": self.error_message,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None
        }


class ModelLoadingManager:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def initiate_load(
        self,
        worker_id: str,
        model_name: str,
        gpu_id: Optional[str] = None
    ) -> WorkerModelInstanceRecord:
        """Initiates loading a model onto a worker, setting status to LOADING (SCH-033)."""
        instance_id = f"inst-{uuid.uuid4().hex[:12]}"
        now = datetime.now(timezone.utc)
        record = WorkerModelInstanceRecord(
            instance_id=instance_id,
            worker_id=worker_id,
            model_name=model_name,
            gpu_id=gpu_id,
            load_status=ModelLoadStatus.LOADING.value,
            loaded_memory_bytes=0,
            load_duration_seconds=0.0,
            error_message=None,
            created_at=now,
            updated_at=now
        )
        self.session.add(record)
        await self.session.commit()
        return record

    async def complete_load(
        self,
        instance_id: str,
        loaded_memory_bytes: int,
        duration_seconds: float
    ) -> WorkerModelInstanceRecord:
        """Transitions instance status to LOADED with residency footprint (SCH-033)."""
        stmt = select(WorkerModelInstanceRecord).where(WorkerModelInstanceRecord.instance_id == instance_id)
        res = await self.session.execute(stmt)
        record = res.scalar_one_or_none()
        if not record:
            raise ValueError(f"Instance '{instance_id}' not found")

        record.load_status = ModelLoadStatus.LOADED.value
        record.loaded_memory_bytes = loaded_memory_bytes
        record.load_duration_seconds = float(duration_seconds)
        record.updated_at = datetime.now(timezone.utc)
        await self.session.commit()
        return record

    async def fail_load(
        self,
        instance_id: str,
        error_message: str
    ) -> WorkerModelInstanceRecord:
        """Transitions instance status to FAILED with error diagnostic (SCH-033)."""
        stmt = select(WorkerModelInstanceRecord).where(WorkerModelInstanceRecord.instance_id == instance_id)
        res = await self.session.execute(stmt)
        record = res.scalar_one_or_none()
        if not record:
            raise ValueError(f"Instance '{instance_id}' not found")

        record.load_status = ModelLoadStatus.FAILED.value
        record.error_message = error_message
        record.updated_at = datetime.now(timezone.utc)
        await self.session.commit()
        return record

    async def unload_model(self, instance_id: str) -> bool:
        """Transitions instance status to UNLOADED (SCH-033)."""
        stmt = select(WorkerModelInstanceRecord).where(WorkerModelInstanceRecord.instance_id == instance_id)
        res = await self.session.execute(stmt)
        record = res.scalar_one_or_none()
        if not record or record.load_status == ModelLoadStatus.UNLOADED.value:
            return False

        record.load_status = ModelLoadStatus.UNLOADED.value
        record.loaded_memory_bytes = 0
        record.updated_at = datetime.now(timezone.utc)
        await self.session.commit()
        return True

    async def get_worker_loaded_models(self, worker_id: str) -> List[WorkerModelInstanceRecord]:
        """Lists active LOADED models resident on a worker (SCH-033)."""
        stmt = (
            select(WorkerModelInstanceRecord)
            .where(
                WorkerModelInstanceRecord.worker_id == worker_id,
                WorkerModelInstanceRecord.load_status == ModelLoadStatus.LOADED.value
            )
        )
        res = await self.session.execute(stmt)
        return list(res.scalars().all())

    async def is_model_loaded_on_worker(self, worker_id: str, model_name: str) -> bool:
        """Checks if a specific model is ready and resident on a worker (SCH-033)."""
        stmt = (
            select(WorkerModelInstanceRecord)
            .where(
                WorkerModelInstanceRecord.worker_id == worker_id,
                WorkerModelInstanceRecord.model_name == model_name,
                WorkerModelInstanceRecord.load_status == ModelLoadStatus.LOADED.value
            )
        )
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none() is not None
