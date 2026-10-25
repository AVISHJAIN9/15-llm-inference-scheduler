import pytest
from scheduler.models import InferenceRequest
from scheduler.admission import AdmissionController, AdmissionReasonCode

def test_SCH_013_admission_rejection():
    """
    SCH-013: Admission rejection.
    Returns structured admission rejection with explicit retryable/non-retryable
    classification and canonical reason codes per cause.
    """
    controller = AdmissionController(
        max_prompt_chars=100,
        max_queue_depth=5,
        allowed_models={"llama-3-8b", "mistral-7b"}
    )

    # 1. Empty prompt -> Non-retryable, EMPTY_PROMPT
    req_empty = InferenceRequest(request_id="r1", model_name="llama-3-8b", prompt="")
    dec_empty = controller.evaluate_admission(req_empty, current_queue_size=0)
    assert dec_empty.admitted is False
    assert dec_empty.retryable is False
    assert dec_empty.reason_code == AdmissionReasonCode.EMPTY_PROMPT

    # 2. Oversized prompt -> Non-retryable, PROMPT_TOO_LARGE
    req_oversized = InferenceRequest(request_id="r2", model_name="llama-3-8b", prompt="x" * 150)
    dec_oversized = controller.evaluate_admission(req_oversized, current_queue_size=0)
    assert dec_oversized.admitted is False
    assert dec_oversized.retryable is False
    assert dec_oversized.reason_code == AdmissionReasonCode.PROMPT_TOO_LARGE

    # 3. Unknown model -> Non-retryable, MODEL_NOT_FOUND
    req_bad_model = InferenceRequest(request_id="r3", model_name="unknown-model", prompt="hello")
    dec_bad_model = controller.evaluate_admission(req_bad_model, current_queue_size=0)
    assert dec_bad_model.admitted is False
    assert dec_bad_model.retryable is False
    assert dec_bad_model.reason_code == AdmissionReasonCode.MODEL_NOT_FOUND

    # 4. Invalid token budget (max_tokens <= 0) -> Non-retryable, INVALID_TOKEN_BUDGET
    req_bad_tokens = InferenceRequest(request_id="r4", model_name="llama-3-8b", prompt="hello", max_tokens=0)
    dec_bad_tokens = controller.evaluate_admission(req_bad_tokens, current_queue_size=0)
    assert dec_bad_tokens.admitted is False
    assert dec_bad_tokens.retryable is False
    assert dec_bad_tokens.reason_code == AdmissionReasonCode.INVALID_TOKEN_BUDGET

    # 5. Queue capacity reached -> Retryable, QUEUE_FULL
    req_queue_full = InferenceRequest(request_id="r5", model_name="llama-3-8b", prompt="hello")
    dec_queue_full = controller.evaluate_admission(req_queue_full, current_queue_size=5)
    assert dec_queue_full.admitted is False
    assert dec_queue_full.retryable is True
    assert dec_queue_full.reason_code == AdmissionReasonCode.QUEUE_FULL

    # 6. Valid request -> Admitted
    req_valid = InferenceRequest(request_id="r6", model_name="llama-3-8b", prompt="hello", max_tokens=64)
    dec_valid = controller.evaluate_admission(req_valid, current_queue_size=2)
    assert dec_valid.admitted is True
    assert dec_valid.retryable is False
    assert dec_valid.reason_code is None
