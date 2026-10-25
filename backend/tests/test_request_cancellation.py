import pytest
import asyncio
from scheduler.models import InferenceRequest, RequestStatus
from scheduler.cancellation import CancellationManager

@pytest.mark.asyncio
async def test_SCH_014_request_cancellation():
    cm = CancellationManager()
    token = cm.register("req-cancel-1")
    assert not token.is_cancelled()
    assert not cm.is_cancelled("req-cancel-1")

    req = InferenceRequest(request_id="req-cancel-1", model_name="gpt-2", prompt="Hello", max_tokens=10)
    assert req.status == RequestStatus.PENDING

    # Cancel request
    res = cm.cancel_request("req-cancel-1", request=req)
    assert res["success"] is True
    assert res["current_status"] == RequestStatus.CANCELLED.value
    assert res["token_signaled"] is True

    # Token and manager reflect cancelled state
    assert token.is_cancelled()
    assert cm.is_cancelled("req-cancel-1")
    assert req.status == RequestStatus.CANCELLED

    # Cleanup
    cm.cleanup("req-cancel-1")
    assert not cm.is_cancelled("req-cancel-1")
