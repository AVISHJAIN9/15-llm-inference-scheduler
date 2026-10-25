import pytest
from scheduler.models import InferenceRequest, RequestStatus
from scheduler.queue import FIFOQueue

def test_SCH_005_fifo_queue_ordering():
    q = FIFOQueue(max_capacity=3)
    assert q.is_empty()
    assert q.size() == 0

    reqs = [
        InferenceRequest(request_id=f"r-{i}", model_name="gpt-2", prompt=f"p-{i}", max_tokens=10)
        for i in range(3)
    ]

    for r in reqs:
        assert q.enqueue(r) is True

    # Capacity overflow test
    overflow_req = InferenceRequest(request_id="overflow", model_name="gpt-2", prompt="p", max_tokens=10)
    assert q.enqueue(overflow_req) is False

    # Duplicate ID test
    assert q.enqueue(reqs[0]) is False

    # Peek check
    peeked = q.peek()
    assert peeked is not None
    assert peeked.request_id == "r-0"

    # Strict FIFO dequeue order
    out = []
    while not q.is_empty():
        item = q.dequeue()
        assert item is not None
        out.append(item.request_id)

    assert out == ["r-0", "r-1", "r-2"]
    assert q.is_empty()
    assert q.dequeue() is None
