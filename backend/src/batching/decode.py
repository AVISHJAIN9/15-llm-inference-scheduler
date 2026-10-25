"""
Decode Batching Engine (SCH-064).
Synchronously batches autoregressive token decoding across active sequences,
advances KV cache slots per step, detects request completion, and reclaims memory.
"""

from typing import Dict, List, Optional, Any
from pydantic import BaseModel
from scheduler.models import InferenceRequest, RequestStatus
from kv.allocator import PagedKVCacheManager


class DecodeBatchResult(BaseModel):
    step_number: int
    active_count: int
    tokens_generated: Dict[str, str]
    finished_request_ids: List[str]


class DecodeSequence:
    def __init__(self, request: InferenceRequest):
        self.request = request
        self.tokens_generated: int = request.tokens_generated or 0
        self.is_finished: bool = False

    @property
    def request_id(self) -> str:
        return self.request.request_id


class DecodeBatcher:
    def __init__(
        self,
        max_decode_batch_size: int = 16,
        kv_manager: Optional[PagedKVCacheManager] = None
    ):
        if max_decode_batch_size <= 0:
            raise ValueError("max_decode_batch_size must be positive")

        self.max_decode_batch_size = max_decode_batch_size
        self.kv_mgr = kv_manager or PagedKVCacheManager(total_blocks=500, block_size=16)
        self.active_sequences: Dict[str, DecodeSequence] = {}
        self.step_counter: int = 0

    @property
    def active_count(self) -> int:
        return len(self.active_sequences)

    def add_decoding_sequence(self, request: InferenceRequest) -> None:
        """Adds an active sequence in DECODE phase to the batch pool (SCH-064)."""
        request.status = RequestStatus.IN_FLIGHT
        seq = DecodeSequence(request)
        self.active_sequences[request.request_id] = seq

    def step(self) -> DecodeBatchResult:
        """
        Executes a single synchronous decode generation step across all active sequences (SCH-064).
        """
        self.step_counter += 1
        tokens_out: Dict[str, str] = {}
        finished: List[str] = []

        batch_items = list(self.active_sequences.values())[:self.max_decode_batch_size]

        for seq in batch_items:
            req_id = seq.request_id
            seq.tokens_generated += 1
            token = f"tok_{seq.tokens_generated}"
            tokens_out[req_id] = token
            seq.request.tokens_generated = seq.tokens_generated

            # Advance KV slot allocation
            self.kv_mgr.append_slot(req_id)

            # Check termination condition
            if seq.tokens_generated >= seq.request.max_tokens:
                seq.is_finished = True
                seq.request.status = RequestStatus.COMPLETED
                finished.append(req_id)
                # Reclaim KV memory
                self.kv_mgr.free(req_id)

        # Remove finished sequences from active decode pool
        for req_id in finished:
            self.active_sequences.pop(req_id, None)

        return DecodeBatchResult(
            step_number=self.step_counter,
            active_count=len(self.active_sequences),
            tokens_generated=tokens_out,
            finished_request_ids=finished
        )
