"""
Continuous Batching Engine, Max Batch Sizing, Token-Budget Batching, and Mixed Prefill/Decode
(SCH-057, SCH-061, SCH-062, SCH-065).
"""

from enum import Enum
from typing import Dict, List, Optional, Tuple, Any
from scheduler.models import InferenceRequest, RequestStatus
from kv.allocator import PagedKVCacheManager

class SequencePhase(str, Enum):
    PREFILL = "PREFILL"
    DECODE = "DECODE"
    FINISHED = "FINISHED"

class BatchSequence:
    def __init__(self, request: InferenceRequest, allocated_blocks: List[int]):
        self.request = request
        self.allocated_blocks = allocated_blocks
        self.generated_tokens: List[str] = []
        self.step_count: int = 0
        self.phase: SequencePhase = SequencePhase.PREFILL
        self.prompt_tokens_count: int = max(1, len(request.prompt.split()))
        self.prefill_processed: int = 0
        self.is_finished: bool = False

    @property
    def request_id(self) -> str:
        return self.request.request_id

class ContinuousBatcher:
    """
    Continuous Batcher supporting:
    - Max batch size enforcement (SCH-061)
    - Token budget limit per iteration (SCH-062)
    - Mixed prefill and decode execution (SCH-065)
    """
    def __init__(
        self,
        max_batch_size: int = 4,
        max_token_budget_per_step: int = 128,
        kv_manager: Optional[PagedKVCacheManager] = None
    ):
        if max_batch_size <= 0:
            raise ValueError("max_batch_size must be positive")
        if max_token_budget_per_step <= 0:
            raise ValueError("max_token_budget_per_step must be positive")

        self.max_batch_size = max_batch_size
        self.max_token_budget_per_step = max_token_budget_per_step
        self.kv_manager = kv_manager or PagedKVCacheManager(total_blocks=500, block_size=16)
        self.active_batch: Dict[str, BatchSequence] = {}
        self.completed_requests: List[InferenceRequest] = []
        self.iteration_count: int = 0

    @property
    def current_batch_size(self) -> int:
        return len(self.active_batch)

    def can_admit(self, request: InferenceRequest) -> bool:
        """Enforces max batch size (SCH-061) and KV memory headroom."""
        if len(self.active_batch) >= self.max_batch_size:
            return False
        prompt_len = max(1, len(request.prompt.split()))
        return self.kv_manager.can_allocate(prompt_len)

    def admit(self, request: InferenceRequest) -> bool:
        """Admit a new sequence into active batch if within max_batch_size (SCH-061)."""
        if not self.can_admit(request):
            return False

        prompt_len = max(1, len(request.prompt.split()))
        blocks = self.kv_manager.allocate(request.request_id, prompt_len)
        if blocks is None:
            return False

        request.status = RequestStatus.IN_FLIGHT
        seq = BatchSequence(request=request, allocated_blocks=blocks)
        self.active_batch[request.request_id] = seq
        return True

    def schedule_iteration(self) -> Tuple[List[BatchSequence], int]:
        """
        Token-budget batch scheduler (SCH-062, SCH-065).
        Selects active sequences up to max_token_budget_per_step.
        Mixed prefill/decode: Prefill consumes prompt tokens; Decode consumes 1 token.
        """
        scheduled: List[BatchSequence] = []
        tokens_budget_used = 0

        # Prioritize ongoing decode sequences, then prefill sequences
        decodes = [s for s in self.active_batch.values() if s.phase == SequencePhase.DECODE]
        prefills = [s for s in self.active_batch.values() if s.phase == SequencePhase.PREFILL]

        # 1. Schedule decodes (1 token each)
        for s in decodes:
            if tokens_budget_used + 1 <= self.max_token_budget_per_step:
                scheduled.append(s)
                tokens_budget_used += 1

        # 2. Schedule prefills within remaining budget
        for s in prefills:
            needed = s.prompt_tokens_count - s.prefill_processed
            if tokens_budget_used + needed <= self.max_token_budget_per_step:
                scheduled.append(s)
                tokens_budget_used += needed

        return scheduled, tokens_budget_used

    def step(self) -> Dict[str, Any]:
        """
        Executes a single continuous iteration step (SCH-057, SCH-062, SCH-065).
        """
        self.iteration_count += 1
        scheduled_seqs, budget_used = self.schedule_iteration()

        step_outputs: Dict[str, str] = {}
        finished_ids: List[str] = []
        prefill_count = 0
        decode_count = 0

        for seq in scheduled_seqs:
            req_id = seq.request_id

            if seq.phase == SequencePhase.PREFILL:
                # Finished prefill phase, generates initial token and transitions to decode
                prefill_count += 1
                seq.prefill_processed = seq.prompt_tokens_count
                seq.step_count += 1
                token = f"tok_init"
                seq.generated_tokens.append(token)
                step_outputs[req_id] = token
                if seq.step_count >= seq.request.max_tokens:
                    seq.phase = SequencePhase.FINISHED
                    seq.is_finished = True
                    finished_ids.append(req_id)
                else:
                    seq.phase = SequencePhase.DECODE
            elif seq.phase == SequencePhase.DECODE:
                decode_count += 1
                seq.step_count += 1
                token = f"tok_{seq.step_count}"
                seq.generated_tokens.append(token)
                step_outputs[req_id] = token
                self.kv_manager.append_slot(req_id)

                if seq.step_count >= seq.request.max_tokens:
                    seq.phase = SequencePhase.FINISHED
                    seq.is_finished = True
                    finished_ids.append(req_id)

        # Retire completed requests
        for req_id in finished_ids:
            seq = self.active_batch.pop(req_id)
            seq.request.status = RequestStatus.COMPLETED
            self.kv_manager.free(req_id)
            self.completed_requests.append(seq.request)

        return {
            "iteration": self.iteration_count,
            "active_count": len(self.active_batch) + len(finished_ids),
            "scheduled_count": len(scheduled_seqs),
            "budget_used": budget_used,
            "prefill_count": prefill_count,
            "decode_count": decode_count,
            "finished_count": len(finished_ids),
            "step_tokens": step_outputs
        }
