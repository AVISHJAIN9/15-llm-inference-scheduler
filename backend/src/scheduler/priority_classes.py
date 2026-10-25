"""
SCH-004: Priority Classes
Defines tiered priority classes for requests, base weights, preemption rights,
and class-based anti-starvation aging logic.
"""

from enum import Enum
from typing import Dict, List, Optional, Union
from pydantic import BaseModel, Field, field_validator
from scheduler.models import InferenceRequest


class PriorityClass(str, Enum):
    CRITICAL = "CRITICAL"
    INTERACTIVE = "INTERACTIVE"
    BATCH = "BATCH"
    BACKGROUND = "BACKGROUND"


class PriorityClassConfig(BaseModel):
    name: str
    base_priority: int = Field(ge=0, description="Base priority score for requests in this class")
    aging_rate: float = Field(default=0.5, ge=0.0, description="Score added per second of wait time")
    can_preempt: bool = Field(default=False, description="Whether this class can preempt lower classes")
    max_wait_seconds: Optional[float] = Field(default=None, ge=0.0, description="SLA deadline threshold")

    @field_validator("base_priority")
    @classmethod
    def validate_base_priority(cls, v: int) -> int:
        if v < 0:
            raise ValueError("base_priority must be non-negative")
        return v

    @field_validator("aging_rate")
    @classmethod
    def validate_aging_rate(cls, v: float) -> float:
        if v < 0.0:
            raise ValueError("aging_rate must be non-negative")
        return v


class PriorityClassRegistry:
    def __init__(self):
        self.classes: Dict[str, PriorityClassConfig] = {}
        self._register_defaults()

    def _register_defaults(self):
        self.register(PriorityClassConfig(
            name=PriorityClass.CRITICAL.value,
            base_priority=100,
            aging_rate=1.0,
            can_preempt=True,
            max_wait_seconds=5.0
        ))
        self.register(PriorityClassConfig(
            name=PriorityClass.INTERACTIVE.value,
            base_priority=50,
            aging_rate=0.5,
            can_preempt=False,
            max_wait_seconds=30.0
        ))
        self.register(PriorityClassConfig(
            name=PriorityClass.BATCH.value,
            base_priority=10,
            aging_rate=0.2,
            can_preempt=False,
            max_wait_seconds=300.0
        ))
        self.register(PriorityClassConfig(
            name=PriorityClass.BACKGROUND.value,
            base_priority=1,
            aging_rate=0.3,
            can_preempt=False,
            max_wait_seconds=1800.0
        ))

    def register(self, config: PriorityClassConfig) -> None:
        self.classes[config.name] = config

    def get_class(self, p_class: Union[PriorityClass, str]) -> PriorityClassConfig:
        key = p_class.value if isinstance(p_class, PriorityClass) else str(p_class).upper()
        if key not in self.classes:
            return self.classes[PriorityClass.BATCH.value]
        return self.classes[key]

    def resolve_class(self, req: InferenceRequest) -> PriorityClassConfig:
        if req.metadata and "priority_class" in req.metadata:
            raw = str(req.metadata["priority_class"]).upper()
            if raw in self.classes:
                return self.classes[raw]

        # Infer from numeric priority if not in metadata
        if req.priority >= 100:
            return self.classes[PriorityClass.CRITICAL.value]
        elif req.priority >= 50:
            return self.classes[PriorityClass.INTERACTIVE.value]
        elif req.priority >= 10:
            return self.classes[PriorityClass.BATCH.value]
        else:
            return self.classes[PriorityClass.BACKGROUND.value]

    def compute_effective_priority(self, req: InferenceRequest, current_time: float) -> float:
        p_class = self.resolve_class(req)
        wait_time = max(0.0, current_time - req.arrival_time)
        return float(p_class.base_priority) + (p_class.aging_rate * wait_time)

    def rank_by_class(self, candidates: List[InferenceRequest], current_time: float) -> List[InferenceRequest]:
        if not candidates:
            return []

        def sort_key(r: InferenceRequest):
            score = self.compute_effective_priority(r, current_time)
            return (-score, r.arrival_time, r.request_id)

        return sorted(candidates, key=sort_key)
