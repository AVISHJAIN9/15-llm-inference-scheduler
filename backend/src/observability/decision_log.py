"""
Request Decision Logging (SCH-115).
Records all scheduler decisions with strict prompt redaction (§9 Invariant).
"""

import time
import json
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, asdict
from enum import Enum
from observability.logging import default_logger


class DecisionType(str, Enum):
    ADMITTED = "ADMITTED"
    QUEUED = "QUEUED"
    REJECTED = "REJECTED"
    PREEMPTED = "PREEMPTED"
    CANCELLED = "CANCELLED"
    COMPLETED = "COMPLETED"


@dataclass
class DecisionRecord:
    timestamp: float
    request_id: str
    tenant_id: str
    model_name: str
    decision: DecisionType
    reason: str
    queue_depth: int
    active_batch_size: int
    kv_free_blocks: int
    prompt_length: int
    prompt_redacted: bool = True

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["decision"] = self.decision.value
        # Guarantee no prompt text is included under any circumstances
        if "prompt" in d:
            del d["prompt"]
        return d




class RequestDecisionLogger:
    """Logs and maintains request scheduling decisions with strict redaction."""

    def __init__(self, max_history: int = 1000):
        self.max_history = max_history
        self._records: List[DecisionRecord] = []

    def record_decision(
        self,
        request_id: str,
        tenant_id: str,
        model_name: str,
        decision: DecisionType,
        reason: str,
        queue_depth: int,
        active_batch_size: int,
        kv_free_blocks: int,
        prompt: Optional[str] = None,
        prompt_length: Optional[int] = None
    ) -> DecisionRecord:
        """
        Records a scheduling decision.
        Invariant (§9): Redacts and excludes raw prompt text entirely.
        """
        calc_length = prompt_length if prompt_length is not None else (len(prompt) if prompt else 0)

        record = DecisionRecord(
            timestamp=time.time(),
            request_id=request_id,
            tenant_id=tenant_id,
            model_name=model_name,
            decision=decision,
            reason=reason,
            queue_depth=queue_depth,
            active_batch_size=active_batch_size,
            kv_free_blocks=kv_free_blocks,
            prompt_length=calc_length,
            prompt_redacted=True
        )

        self._records.append(record)
        if len(self._records) > self.max_history:
            self._records.pop(0)

        # Emit structured log without any prompt text
        default_logger.info(
            "Scheduler decision logged",
            event="SCHEDULER_DECISION",
            request_id=request_id,
            tenant_id=tenant_id,
            model_name=model_name,
            decision=decision.value,
            reason=reason,
            queue_depth=queue_depth,
            active_batch_size=active_batch_size,
            kv_free_blocks=kv_free_blocks,
            prompt_length=calc_length,
            prompt="[REDACTED]"
        )

        return record

    def get_records(self, limit: int = 100) -> List[Dict[str, Any]]:
        return [r.to_dict() for r in self._records[-limit:]]

    def clear(self) -> None:
        self._records.clear()


default_decision_logger = RequestDecisionLogger()
