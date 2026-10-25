"""
Prefill Batching Engine (SCH-063).
Batches compute-bound prompt evaluations across multiple inference requests,
enforces maximum prompt token limits, and coordinates transition to token decoding.
"""

import uuid
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, ConfigDict
from scheduler.models import InferenceRequest, RequestStatus
from kv.allocator import PagedKVCacheManager


class PrefillSequence:
    def __init__(self, request: InferenceRequest, prompt_tokens: int, allocated_blocks: Optional[List[int]] = None):
        self.request = request
        self.prompt_tokens_count = prompt_tokens
        self.prefill_processed = 0
        self.phase = "PREFILL"
        self.allocated_blocks = allocated_blocks or []

    @property
    def request_id(self) -> str:
        return self.request.request_id


class PrefillBatch:
    def __init__(self, batch_id: str, sequences: List[PrefillSequence], total_prompt_tokens: int):
        self.batch_id = batch_id
        self.sequences = sequences
        self.total_prompt_tokens = total_prompt_tokens


class PrefillExecutionResult(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    batch_id: str
    completed_prefills: List[Any]
    tokens_processed: int


class PrefillBatcher:
    def __init__(
        self,
        max_prefill_tokens: int = 4096,
        max_sequences: int = 16,
        kv_manager: Optional[PagedKVCacheManager] = None
    ):
        if max_prefill_tokens <= 0:
            raise ValueError("max_prefill_tokens must be positive")
        if max_sequences <= 0:
            raise ValueError("max_sequences must be positive")

        self.max_prefill_tokens = max_prefill_tokens
        self.max_sequences = max_sequences
        self.kv_mgr = kv_manager or PagedKVCacheManager(total_blocks=500, block_size=16)
        self._pending: List[InferenceRequest] = []

    def enqueue(self, request: InferenceRequest) -> None:
        """Enqueues a request waiting for prompt prefill evaluation (SCH-063)."""
        request.status = RequestStatus.QUEUED
        self._pending.append(request)

    def form_prefill_batch(self) -> Optional[PrefillBatch]:
        """
        Forms a prefill batch respecting maximum prefill token and sequence limits (SCH-063).
        """
        if not self._pending:
            return None

        batch_sequences: List[PrefillSequence] = []
        tokens_accumulated = 0
        deferred: List[InferenceRequest] = []

        for req in self._pending:
            prompt_tokens = max(1, len(req.prompt.split()))
            if (
                tokens_accumulated + prompt_tokens <= self.max_prefill_tokens
                and len(batch_sequences) < self.max_sequences
            ):
                # Allocate KV blocks for prompt if not already allocated
                blocks = self.kv_mgr.allocate(req.request_id, prompt_tokens)
                if blocks is not None:
                    req.status = RequestStatus.IN_FLIGHT
                    seq = PrefillSequence(req, prompt_tokens, blocks)
                    batch_sequences.append(seq)
                    tokens_accumulated += prompt_tokens
                else:
                    deferred.append(req)
            else:
                deferred.append(req)

        self._pending = deferred

        if not batch_sequences:
            return None

        batch_id = f"prefill-{uuid.uuid4().hex[:12]}"
        return PrefillBatch(
            batch_id=batch_id,
            sequences=batch_sequences,
            total_prompt_tokens=tokens_accumulated
        )

    def execute_prefill_batch(self, batch: PrefillBatch) -> PrefillExecutionResult:
        """
        Executes prefill for all batched sequences, processing prompt tokens and
        transitioning sequences to DECODE phase (SCH-063).
        """
        completed: List[PrefillSequence] = []
        tokens_done = 0

        for seq in batch.sequences:
            seq.prefill_processed = seq.prompt_tokens_count
            seq.phase = "DECODE"
            seq.request.tokens_generated = 1  # Initial prompt token produced
            tokens_done += seq.prompt_tokens_count
            completed.append(seq)

        return PrefillExecutionResult(
            batch_id=batch.batch_id,
            completed_prefills=completed,
            tokens_processed=tokens_done
        )
