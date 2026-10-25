"""
Request Admission Controller (SCH-002, SCH-013).
Validates prompt size, model availability, queue depth limits, and token budgets.
Classifies admission rejections with explicit retryable flags and canonical reason codes.
"""

from enum import Enum
from typing import Set, Optional
from scheduler.models import InferenceRequest, AdmissionDecision, RequestStatus
from clock import Clock


class AdmissionReasonCode(str, Enum):
    EMPTY_PROMPT = "EMPTY_PROMPT"
    PROMPT_TOO_LARGE = "PROMPT_TOO_LARGE"
    MODEL_NOT_FOUND = "MODEL_NOT_FOUND"
    QUEUE_FULL = "QUEUE_FULL"
    INVALID_TOKEN_BUDGET = "INVALID_TOKEN_BUDGET"
    TENANT_QUOTA_EXCEEDED = "TENANT_QUOTA_EXCEEDED"


class AdmissionController:
    def __init__(
        self,
        max_prompt_chars: int = 32000,
        max_queue_depth: int = 1000,
        allowed_models: Optional[Set[str]] = None,
        clock: Optional[Clock] = None
    ):
        self.max_prompt_chars = max_prompt_chars
        self.max_queue_depth = max_queue_depth
        self.allowed_models = allowed_models or {"llama-3-8b", "qwen-0.5b", "mistral-7b", "gpt-neox"}
        self.clock = clock or Clock()

    def evaluate_admission(self, request: InferenceRequest, current_queue_size: int) -> AdmissionDecision:
        # Prompt length check
        if not request.prompt:
            request.status = RequestStatus.REJECTED
            request.error_message = "Prompt cannot be empty"
            return AdmissionDecision(
                admitted=False,
                reason=request.error_message,
                retryable=False,
                reason_code=AdmissionReasonCode.EMPTY_PROMPT,
                request=request
            )

        if len(request.prompt) > self.max_prompt_chars:
            request.status = RequestStatus.REJECTED
            request.error_message = f"Prompt exceeds maximum character limit of {self.max_prompt_chars}"
            return AdmissionDecision(
                admitted=False,
                reason=request.error_message,
                retryable=False,
                reason_code=AdmissionReasonCode.PROMPT_TOO_LARGE,
                request=request
            )

        # Model support check
        if request.model_name not in self.allowed_models:
            request.status = RequestStatus.REJECTED
            request.error_message = f"Model '{request.model_name}' is not in allowed models: {sorted(self.allowed_models)}"
            return AdmissionDecision(
                admitted=False,
                reason=request.error_message,
                retryable=False,
                reason_code=AdmissionReasonCode.MODEL_NOT_FOUND,
                request=request
            )

        # Queue capacity check (retryable when backpressure clears)
        if current_queue_size >= self.max_queue_depth:
            request.status = RequestStatus.REJECTED
            request.error_message = f"Scheduler queue is at maximum capacity ({self.max_queue_depth})"
            return AdmissionDecision(
                admitted=False,
                reason=request.error_message,
                retryable=True,
                reason_code=AdmissionReasonCode.QUEUE_FULL,
                request=request
            )

        # Token bounds check
        if request.max_tokens <= 0:
            request.status = RequestStatus.REJECTED
            request.error_message = "max_tokens must be greater than zero"
            return AdmissionDecision(
                admitted=False,
                reason=request.error_message,
                retryable=False,
                reason_code=AdmissionReasonCode.INVALID_TOKEN_BUDGET,
                request=request
            )

        # Admitted successfully
        request.status = RequestStatus.ADMITTED
        if request.arrival_time <= 0:
            request.arrival_time = self.clock.now()
        request.effective_priority = float(request.priority)
        return AdmissionDecision(
            admitted=True,
            reason=None,
            retryable=False,
            reason_code=None,
            request=request
        )

    admit = evaluate_admission
