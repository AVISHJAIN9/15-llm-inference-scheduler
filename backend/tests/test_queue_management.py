import pytest
from scheduler.models import InferenceRequest, RequestStatus
from scheduler.queue import QueueManager, FIFOQueue

def test_SCH_003_queue_management():
    qm = QueueManager(fifo_queue=FIFOQueue(max_capacity=5))
    assert qm.depth() == 0

    req1 = InferenceRequest(request_id="req-1", model_name="gpt-2", prompt="Hello", max_tokens=10)
    req2 = InferenceRequest(request_id="req-2", model_name="gpt-2", prompt="World", max_tokens=20)
    req3 = InferenceRequest(request_id="req-3", model_name="gpt-2", prompt="Test", max_tokens=30)

    # Submit
    assert qm.submit(req1) is True
    assert qm.submit(req2) is True
    assert qm.submit(req3) is True
    assert qm.depth() == 3

    # Status check
    assert req1.status == RequestStatus.QUEUED

    # Cancellation
    cancelled = qm.cancel("req-2")
    assert cancelled is not None
    assert cancelled.request_id == "req-2"
    assert cancelled.status == RequestStatus.CANCELLED
    assert qm.depth() == 2

    # Pop next yields req-1, then req-3
    p1 = qm.pop_next()
    assert p1.request_id == "req-1"
    assert qm.depth() == 1

    p2 = qm.pop_next()
    assert p2.request_id == "req-3"
    assert qm.depth() == 0

    # Pop on empty
    assert qm.pop_next() is None
