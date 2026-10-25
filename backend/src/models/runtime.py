"""
Inference Runtime Selection and Compatibility Engine (SCH-042).
Manages hardware acceleration compatibility (GPU compute capabilities,
speculative decoding, chunked prefill) and selects optimal runtimes (vLLM, TensorRT-LLM, ONNX).
"""

import uuid
from enum import Enum
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
from sqlalchemy import Column, String, Integer, Float, Boolean, DateTime, select
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, ConfigDict
from db.database import Base


class RuntimeEngineType(str, Enum):
    VLLM = "vllm"
    TENSORRT_LLM = "tensorrt_llm"
    TGI = "tgi"
    ONNX_RUNTIME = "onnx_runtime"


class ModelRuntimeRecord(Base):
    __tablename__ = "model_runtime_configs"

    config_id = Column(String(64), primary_key=True)
    model_name = Column(String(128), nullable=False, index=True)
    runtime_engine = Column(String(64), nullable=False)
    min_compute_capability = Column(Float, default=7.0, nullable=False)
    supports_chunked_prefill = Column(Boolean, default=True, nullable=False)
    supports_speculative_decoding = Column(Boolean, default=False, nullable=False)
    max_batch_tokens = Column(Integer, default=8192, nullable=False)
    is_preferred = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "config_id": self.config_id,
            "model_name": self.model_name,
            "runtime_engine": self.runtime_engine,
            "min_compute_capability": self.min_compute_capability,
            "supports_chunked_prefill": self.supports_chunked_prefill,
            "supports_speculative_decoding": self.supports_speculative_decoding,
            "max_batch_tokens": self.max_batch_tokens,
            "is_preferred": self.is_preferred,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class RuntimeEngineConfig(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    config_id: Optional[str] = None
    model_name: str
    runtime_engine: RuntimeEngineType
    min_compute_capability: float = 7.0
    supports_chunked_prefill: bool = True
    supports_speculative_decoding: bool = False
    max_batch_tokens: int = 8192
    is_preferred: bool = False


class RuntimeSelector:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def register_runtime_config(self, config: RuntimeEngineConfig) -> RuntimeEngineConfig:
        config_id = config.config_id or f"cfg-{uuid.uuid4().hex[:12]}"
        record = ModelRuntimeRecord(
            config_id=config_id,
            model_name=config.model_name,
            runtime_engine=config.runtime_engine.value,
            min_compute_capability=config.min_compute_capability,
            supports_chunked_prefill=config.supports_chunked_prefill,
            supports_speculative_decoding=config.supports_speculative_decoding,
            max_batch_tokens=config.max_batch_tokens,
            is_preferred=config.is_preferred,
            created_at=datetime.now(timezone.utc)
        )
        self.session.add(record)
        await self.session.commit()
        return RuntimeEngineConfig.model_validate(record)

    async def select_optimal_runtime(
        self,
        model_name: str,
        gpu_compute_capability: float,
        require_speculative_decoding: bool = False,
        require_chunked_prefill: bool = False
    ) -> Optional[RuntimeEngineConfig]:
        stmt = (
            select(ModelRuntimeRecord)
            .where(ModelRuntimeRecord.model_name == model_name)
        )
        res = await self.session.execute(stmt)
        records = res.scalars().all()

        compatible: List[ModelRuntimeRecord] = []
        for r in records:
            # Check hardware compute capability
            if gpu_compute_capability < r.min_compute_capability:
                continue

            # Check feature requirements
            if require_speculative_decoding and not r.supports_speculative_decoding:
                continue
            if require_chunked_prefill and not r.supports_chunked_prefill:
                continue

            compatible.append(r)

        if not compatible:
            return None

        # Sort: preferred first, then highest compute capability, then highest batch tokens
        compatible.sort(
            key=lambda r: (
                1 if r.is_preferred else 0,
                r.min_compute_capability,
                r.max_batch_tokens
            ),
            reverse=True
        )

        return RuntimeEngineConfig.model_validate(compatible[0])

    async def list_runtime_configs(self, model_name: str) -> List[RuntimeEngineConfig]:
        stmt = (
            select(ModelRuntimeRecord)
            .where(ModelRuntimeRecord.model_name == model_name)
            .order_by(ModelRuntimeRecord.is_preferred.desc(), ModelRuntimeRecord.created_at.asc())
        )
        res = await self.session.execute(stmt)
        records = res.scalars().all()
        return [RuntimeEngineConfig.model_validate(r) for r in records]
