"""
SCH-001: Scheduler Policy Model
Defines the configurable policy abstractions and evaluation logic
for scheduling inference requests across GPU workers.
"""

from enum import Enum
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, field_validator
from scheduler.models import InferenceRequest


class PolicyType(str, Enum):
    FIFO = "FIFO"
    PRIORITY = "PRIORITY"
    WEIGHTED_FAIR = "WEIGHTED_FAIR"
    DEADLINE_AWARE = "DEADLINE_AWARE"


class SchedulerPolicyConfig(BaseModel):
    policy_type: PolicyType = PolicyType.FIFO
    aging_factor: float = Field(default=0.1, description="Rate at which priority increases with wait time")
    deadline_slack_seconds: float = Field(default=0.0, description="Minimum buffer time before deadline")
    quantum: float = Field(default=1.0, description="Base scheduling quantum for weighted fair queue")

    @field_validator("aging_factor")
    @classmethod
    def validate_aging_factor(cls, v: float) -> float:
        if v < 0.0:
            raise ValueError("aging_factor must be non-negative")
        return v

    @field_validator("deadline_slack_seconds")
    @classmethod
    def validate_deadline_slack(cls, v: float) -> float:
        if v < 0.0:
            raise ValueError("deadline_slack_seconds must be non-negative")
        return v

    @field_validator("quantum")
    @classmethod
    def validate_quantum(cls, v: float) -> float:
        if v <= 0.0:
            raise ValueError("quantum must be strictly positive")
        return v


class SchedulerPolicyModel:
    def __init__(self, config: Optional[SchedulerPolicyConfig] = None):
        self.config = config or SchedulerPolicyConfig()

    @property
    def current_policy(self) -> PolicyType:
        return self.config.policy_type

    def set_policy(self, policy_type: PolicyType, **kwargs) -> None:
        updated_dict = self.config.model_dump()
        updated_dict["policy_type"] = policy_type
        for k, v in kwargs.items():
            if k in updated_dict:
                updated_dict[k] = v
        self.config = SchedulerPolicyConfig(**updated_dict)

    def calculate_effective_priority(self, req: InferenceRequest, current_time: float) -> float:
        wait_time = max(0.0, current_time - req.arrival_time)
        return float(req.priority) + (self.config.aging_factor * wait_time)

    def rank_candidates(self, candidates: List[InferenceRequest], current_time: float) -> List[InferenceRequest]:
        if not candidates:
            return []

        if self.current_policy == PolicyType.FIFO:
            return sorted(candidates, key=lambda r: (r.arrival_time, r.request_id))

        elif self.current_policy == PolicyType.PRIORITY:
            return sorted(
                candidates,
                key=lambda r: (-self.calculate_effective_priority(r, current_time), r.arrival_time, r.request_id)
            )

        elif self.current_policy == PolicyType.DEADLINE_AWARE:
            def deadline_sort_key(r: InferenceRequest):
                dl = r.deadline if r.deadline is not None else float("inf")
                return (dl, r.arrival_time, r.request_id)

            return sorted(candidates, key=deadline_sort_key)

        elif self.current_policy == PolicyType.WEIGHTED_FAIR:
            def vft_key(r: InferenceRequest):
                w = max(0.001, float(r.weight))
                tokens = max(1, r.max_tokens)
                vft = r.arrival_time + (tokens / w)
                return (vft, r.arrival_time, r.request_id)

            return sorted(candidates, key=vft_key)

        return list(candidates)

    def select_next(self, candidates: List[InferenceRequest], current_time: float) -> Optional[InferenceRequest]:
        ranked = self.rank_candidates(candidates, current_time)
        return ranked[0] if ranked else None
