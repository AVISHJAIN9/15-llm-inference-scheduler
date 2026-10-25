import pytest
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root / "src"))

from scheduler.models import InferenceRequest, RequestStatus
from scheduler.admission import AdmissionController
from clock import Clock

def test_SCH_002_request_admission_valid():
    """SCH-002: Verify valid request admission and state transition."""
    clock = Clock(initial_time=1000.0)
    controller = AdmissionController(clock=clock)

    req = InferenceRequest(
        request_id="req-002-1",
        model_name="qwen-0.5b",
        prompt="Explain KV cache in 2 sentences.",
        max_tokens=64
    )
    decision = controller.evaluate_admission(req, current_queue_size=10)

    assert decision.admitted is True
    assert decision.reason is None
    assert req.status == RequestStatus.ADMITTED
    assert req.arrival_time == 1000.0

def test_SCH_002_request_admission_rejections():
    """SCH-002: Verify rejection on disallowed model, empty prompt, and capacity limits."""
    controller = AdmissionController(max_queue_depth=50, max_prompt_chars=100)

    # Unknown model rejection
    req_bad_model = InferenceRequest(
        request_id="req-bad-model",
        model_name="unknown-gpt-99",
        prompt="hello"
    )
    d1 = controller.evaluate_admission(req_bad_model, current_queue_size=0)
    assert d1.admitted is False
    assert "not in allowed models" in d1.reason

    # Prompt overflow
    req_long = InferenceRequest(
        request_id="req-long",
        model_name="qwen-0.5b",
        prompt="x" * 150
    )
    d2 = controller.evaluate_admission(req_long, current_queue_size=0)
    assert d2.admitted is False
    assert "exceeds maximum character limit" in d2.reason

    # Queue full rejection
    req_full = InferenceRequest(
        request_id="req-full",
        model_name="qwen-0.5b",
        prompt="valid prompt"
    )
    d3 = controller.evaluate_admission(req_full, current_queue_size=50)
    assert d3.admitted is False
    assert "maximum capacity" in d3.reason
