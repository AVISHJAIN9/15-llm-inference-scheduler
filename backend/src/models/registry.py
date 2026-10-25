"""
Model Registry database schema and management (SCH-029).
Tracks active model architectures, context windows, memory profiles, and runtime configurations.
"""

from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from sqlalchemy import Column, String, Integer, BigInteger, Boolean, DateTime, select
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, ConfigDict
from db.database import Base

class ModelRecord(Base):
    __tablename__ = "model_registry"

    model_name = Column(String(128), primary_key=True, index=True)
    architecture = Column(String(64), nullable=False)
    max_context_length = Column(Integer, nullable=False)
    required_memory_bytes = Column(BigInteger, nullable=False)
    weights_uri = Column(String(256), nullable=False)
    parameter_count = Column(BigInteger, nullable=True)
    quantization = Column(String(32), default="fp16", nullable=False)
    num_layers = Column(Integer, nullable=True)
    num_heads = Column(Integer, nullable=True)
    num_kv_heads = Column(Integer, nullable=True)
    hidden_size = Column(Integer, nullable=True)
    vocab_size = Column(Integer, nullable=True)
    tensor_parallel_size = Column(Integer, default=1, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    def to_dict(self):
        return {
            "model_name": self.model_name,
            "architecture": self.architecture,
            "max_context_length": self.max_context_length,
            "required_memory_bytes": self.required_memory_bytes,
            "weights_uri": self.weights_uri,
            "parameter_count": self.parameter_count,
            "quantization": self.quantization,
            "num_layers": self.num_layers,
            "num_heads": self.num_heads,
            "num_kv_heads": self.num_kv_heads,
            "hidden_size": self.hidden_size,
            "vocab_size": self.vocab_size,
            "tensor_parallel_size": self.tensor_parallel_size,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }

SUPPORTED_QUANTIZATIONS = {"fp32", "fp16", "bf16", "int8", "int4", "awq", "gptq"}

class ModelSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    model_name: str
    architecture: str
    max_context_length: int
    required_memory_bytes: int
    weights_uri: str
    parameter_count: Optional[int] = None
    quantization: str = "fp16"
    num_layers: Optional[int] = None
    num_heads: Optional[int] = None
    num_kv_heads: Optional[int] = None
    hidden_size: Optional[int] = None
    vocab_size: Optional[int] = None
    tensor_parallel_size: int = 1
    is_active: bool = True

class ModelRegistry:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def register_model(self, schema: ModelSchema) -> ModelSchema:
        if schema.max_context_length <= 0:
            raise ValueError("max_context_length must be positive")
        if schema.required_memory_bytes <= 0:
            raise ValueError("required_memory_bytes must be positive")
        if schema.parameter_count is not None and schema.parameter_count <= 0:
            raise ValueError("parameter_count must be positive")
        if schema.quantization and schema.quantization.lower() not in SUPPORTED_QUANTIZATIONS:
            raise ValueError(f"quantization '{schema.quantization}' not in supported: {sorted(SUPPORTED_QUANTIZATIONS)}")

        stmt = select(ModelRecord).where(ModelRecord.model_name == schema.model_name)
        res = await self.session.execute(stmt)
        record = res.scalar_one_or_none()

        if record:
            record.architecture = schema.architecture
            record.max_context_length = schema.max_context_length
            record.required_memory_bytes = schema.required_memory_bytes
            record.weights_uri = schema.weights_uri
            record.parameter_count = schema.parameter_count
            record.quantization = schema.quantization.lower()
            record.num_layers = schema.num_layers
            record.num_heads = schema.num_heads
            record.num_kv_heads = schema.num_kv_heads
            record.hidden_size = schema.hidden_size
            record.vocab_size = schema.vocab_size
            record.tensor_parallel_size = schema.tensor_parallel_size
            record.is_active = schema.is_active
        else:
            record = ModelRecord(
                model_name=schema.model_name,
                architecture=schema.architecture,
                max_context_length=schema.max_context_length,
                required_memory_bytes=schema.required_memory_bytes,
                weights_uri=schema.weights_uri,
                parameter_count=schema.parameter_count,
                quantization=schema.quantization.lower(),
                num_layers=schema.num_layers,
                num_heads=schema.num_heads,
                num_kv_heads=schema.num_kv_heads,
                hidden_size=schema.hidden_size,
                vocab_size=schema.vocab_size,
                tensor_parallel_size=schema.tensor_parallel_size,
                is_active=schema.is_active
            )
            self.session.add(record)

        await self.session.commit()
        return ModelSchema.model_validate(record)

    async def get_model(self, model_name: str) -> Optional[ModelSchema]:
        stmt = select(ModelRecord).where(ModelRecord.model_name == model_name)
        res = await self.session.execute(stmt)
        record = res.scalar_one_or_none()
        if not record:
            return None
        return ModelSchema.model_validate(record)

    async def list_active_models(self) -> List[ModelSchema]:
        stmt = select(ModelRecord).where(ModelRecord.is_active == True)
        res = await self.session.execute(stmt)
        records = res.scalars().all()
        return [ModelSchema.model_validate(r) for r in records]
