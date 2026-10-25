import pytest
from scheduler.models import InferenceRequest, RequestStatus
from scheduler.queue import PriorityQueue

def test_SCH_006_priority_queue():
    pq = PriorityQueue(max_capacity=10)
    assert pq.is_empty()

    # Insert requests with varying priorities: 1 (low), 10 (high), 5 (medium)
    r_low = InferenceRequest(request_id="low", model_name="gpt-2", prompt="p", max_tokens=10, priority=1, arrival_time=100.0)
    r_high = InferenceRequest(request_id="high", model_name="gpt-2", prompt="p", max_tokens=10, priority=10, arrival_time=101.0)
    r_med = InferenceRequest(request_id="med", model_name="gpt-2", prompt="p", max_tokens=10, priority=5, arrival_time=102.0)
    r_med2 = InferenceRequest(request_id="med2", model_name="gpt-2", prompt="p", max_tokens=10, priority=5, arrival_time=103.0)

    pq.enqueue(r_low)
    pq.enqueue(r_high)
    pq.enqueue(r_med)
    pq.enqueue(r_med2)

    assert pq.size() == 4

    # Dequeue order should strictly be: high (10) -> med (5, arrived earlier) -> med2 (5, arrived later) -> low (1)
    d1 = pq.dequeue()
    assert d1.request_id == "high"

    d2 = pq.dequeue()
    assert d2.request_id == "med"

    d3 = pq.dequeue()
    assert d3.request_id == "med2"

    d4 = pq.dequeue()
    assert d4.request_id == "low"

    assert pq.is_empty()
    assert pq.dequeue() is None
