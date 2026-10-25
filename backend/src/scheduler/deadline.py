"""
SCH-008: Deadline-Aware Scheduling
Implements Earliest Feasible Deadline First (EDF) scheduling.
Evaluates deadline feasibility based on estimated execution latency.
Infeasible requests are deprioritized or rejected per configured policy.
"""

from enum import Enum
from typing import List, Optional
from scheduler.models import InferenceRequest


class InfeasibleDeadlineAction(str, Enum):
    DEPRIORITIZE = "DEPRIORITIZE"
    REJECT = "REJECT"


class DeadlineScheduler:
    def __init__(
        self,
        tokens_per_sec: float = 20.0,
        time_to_first_token: float = 0.05,
        infeasible_action: InfeasibleDeadlineAction = InfeasibleDeadlineAction.DEPRIORITIZE
    ):
        self.tokens_per_sec = max(0.1, tokens_per_sec)
        self.time_to_first_token = max(0.0, time_to_first_token)
        self.infeasible_action = infeasible_action

    def estimate_execution_time(self, req: InferenceRequest) -> float:
        num_tokens = max(1, req.max_tokens)
        return self.time_to_first_token + (num_tokens / self.tokens_per_sec)

    def is_feasible(self, req: InferenceRequest, current_time: float) -> bool:
        if req.deadline is None:
            return True
        estimated_finish = current_time + self.estimate_execution_time(req)
        return estimated_finish <= req.deadline

    def rank_candidates(
        self,
        candidates: List[InferenceRequest],
        current_time: float
    ) -> List[InferenceRequest]:
        if not candidates:
            return []

        feasible_with_dl: List[InferenceRequest] = []
        feasible_no_dl: List[InferenceRequest] = []
        infeasible: List[InferenceRequest] = []

        for req in candidates:
            if self.is_feasible(req, current_time):
                if req.deadline is not None:
                    feasible_with_dl.append(req)
                else:
                    feasible_no_dl.append(req)
            else:
                infeasible.append(req)

        # 1. Feasible requests sorted by deadline ascending
        feasible_with_dl.sort(key=lambda r: (r.deadline, r.arrival_time, r.request_id))

        # 2. Feasible requests without explicit deadline sorted by arrival time
        feasible_no_dl.sort(key=lambda r: (r.arrival_time, r.request_id))

        if self.infeasible_action == InfeasibleDeadlineAction.REJECT:
            return feasible_with_dl + feasible_no_dl

        # 3. Infeasible requests deprioritized (sorted by arrival time)
        infeasible.sort(key=lambda r: (r.arrival_time, r.request_id))
        return feasible_with_dl + feasible_no_dl + infeasible

    def select_next(
        self,
        candidates: List[InferenceRequest],
        current_time: float
    ) -> Optional[InferenceRequest]:
        ranked = self.rank_candidates(candidates, current_time)
        return ranked[0] if ranked else None
