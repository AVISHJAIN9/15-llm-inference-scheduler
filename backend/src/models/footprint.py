"""
Model Memory Footprint Calculator and SQL Persistence (SCH-038).
Computes exact weight memory, activation buffers, workspace scratchpad,
and per-GPU tensor parallel allocations per quantization precision.
"""

import uuid
from enum import Enum
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from sqlalchemy import Column, String, Integer, BigInteger, DateTime, select
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, ConfigDict, Field
from db.database import Base


class PrecisionBytes(float, Enum):
    FP32 = 4.0
    FP16 = 2.0
    BF16 = 2.0
    FP8 = 1.0
    INT8 = 1.0
    INT4 = 0.5
    AWQ = 0.5
    GPTQ = 0.5


PRECISION_MAP: Dict[str, float] = {
    "fp32": 4.0,
    "fp16": 2.0,
    "bf16": 2.0,
    "fp8": 1.0,
    "int8": 1.0,
    "int4": 0.5,
    "awq": 0.5,
    "gptq": 0.5,
}


class MemoryFootprintResult(BaseModel):
    parameter_count: int
    quantization: str
    weight_memory_bytes: int
    activation_overhead_bytes: int
    workspace_overhead_bytes: int
    total_required_bytes: int
    tensor_parallel_size: int = 1
    per_gpu_weight_bytes: int
    per_gpu_memory_bytes: int


class ModelMemoryFootprintRecord(Base):
    __tablename__ = "model_memory_footprints"

    footprint_id = Column(String(64), primary_key=True)
    model_name = Column(String(128), nullable=False, index=True)
    quantization = Column(String(32), nullable=False)
    parameter_count = Column(BigInteger, nullable=False)
    weight_memory_bytes = Column(BigInteger, nullable=False)
    activation_overhead_bytes = Column(BigInteger, nullable=False)
    workspace_overhead_bytes = Column(BigInteger, nullable=False)
    total_required_bytes = Column(BigInteger, nullable=False)
    tensor_parallel_size = Column(Integer, default=1, nullable=False)
    per_gpu_memory_bytes = Column(BigInteger, nullable=False)
    calculated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "footprint_id": self.footprint_id,
            "model_name": self.model_name,
            "quantization": self.quantization,
            "parameter_count": self.parameter_count,
            "weight_memory_bytes": self.weight_memory_bytes,
            "activation_overhead_bytes": self.activation_overhead_bytes,
            "workspace_overhead_bytes": self.workspace_overhead_bytes,
            "total_required_bytes": self.total_required_bytes,
            "tensor_parallel_size": self.tensor_parallel_size,
            "per_gpu_memory_bytes": self.per_gpu_memory_bytes,
            "calculated_at": self.calculated_at.isoformat() if self.calculated_at else None,
        }


class ModelMemoryFootprintSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    footprint_id: str
    model_name: str
    quantization: str
    parameter_count: int
    weight_memory_bytes: int
    activation_overhead_bytes: int
    workspace_overhead_bytes: int
    total_required_bytes: int
    tensor_parallel_size: int = 1
    per_gpu_memory_bytes: int


class MemoryFootprintCalculator:
    def get_bytes_per_param(self, quantization: str) -> float:
        q_lower = quantization.lower()
        if q_lower not in PRECISION_MAP:
            raise ValueError(f"Unsupported quantization '{quantization}'. Supported: {sorted(PRECISION_MAP.keys())}")
        return PRECISION_MAP[q_lower]

    def compute_footprint(
        self,
        parameter_count: int,
        quantization: str = "fp16",
        max_context_length: int = 4096,
        hidden_size: int = 4096,
        num_layers: int = 32,
        tensor_parallel_size: int = 1
    ) -> MemoryFootprintResult:
        if parameter_count <= 0:
            raise ValueError("parameter_count must be strictly positive")
        if tensor_parallel_size <= 0:
            raise ValueError("tensor_parallel_size must be at least 1")

        bytes_per_param = self.get_bytes_per_param(quantization)
        weight_bytes = int(parameter_count * bytes_per_param)

        # Activation memory overhead estimation:
        # Standard transformer activation buffer ~ 2 * max_context_length * hidden_size * num_layers * bytes_per_elem
        activation_bytes = int(2 * max_context_length * hidden_size * (num_layers / 8) * 2)

        # Workspace scratchpad buffer (cuBLAS workspace, kv workspace) ~ 256 MB base
        workspace_bytes = 256 * 1024 * 1024

        total_bytes = weight_bytes + activation_bytes + workspace_bytes

        # Tensor parallel distribution
        per_gpu_weight = weight_bytes // tensor_parallel_size
        per_gpu_act = activation_bytes // tensor_parallel_size
        per_gpu_total = per_gpu_weight + per_gpu_act + workspace_bytes

        return MemoryFootprintResult(
            parameter_count=parameter_count,
            quantization=quantization.lower(),
            weight_memory_bytes=weight_bytes,
            activation_overhead_bytes=activation_bytes,
            workspace_overhead_bytes=workspace_bytes,
            total_required_bytes=total_bytes,
            tensor_parallel_size=tensor_parallel_size,
            per_gpu_weight_bytes=per_gpu_weight,
            per_gpu_memory_bytes=per_gpu_total
        )


class ModelMemoryFootprintManager:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def store_footprint(
        self,
        model_name: str,
        footprint: MemoryFootprintResult
    ) -> ModelMemoryFootprintSchema:
        footprint_id = f"fp-{uuid.uuid4().hex[:12]}"
        record = ModelMemoryFootprintRecord(
            footprint_id=footprint_id,
            model_name=model_name,
            quantization=footprint.quantization,
            parameter_count=footprint.parameter_count,
            weight_memory_bytes=footprint.weight_memory_bytes,
            activation_overhead_bytes=footprint.activation_overhead_bytes,
            workspace_overhead_bytes=footprint.workspace_overhead_bytes,
            total_required_bytes=footprint.total_required_bytes,
            tensor_parallel_size=footprint.tensor_parallel_size,
            per_gpu_memory_bytes=footprint.per_gpu_memory_bytes,
            calculated_at=datetime.now(timezone.utc)
        )
        self.session.add(record)
        await self.session.commit()
        return ModelMemoryFootprintSchema.model_validate(record)

    async def get_footprint(self, model_name: str) -> Optional[ModelMemoryFootprintSchema]:
        stmt = (
            select(ModelMemoryFootprintRecord)
            .where(ModelMemoryFootprintRecord.model_name == model_name)
            .order_by(ModelMemoryFootprintRecord.calculated_at.desc())
        )
        res = await self.session.execute(stmt)
        record = res.scalar_one_or_none()
        if not record:
            return None
        return ModelMemoryFootprintSchema.model_validate(record)
