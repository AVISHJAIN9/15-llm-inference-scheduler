import pytest
from clock import Clock
from scheduler.models import InferenceRequest
from scheduler.queue import PriorityQueue

def test_SCH_011_queue_aging_prevents_starvation():
    clk = Clock(initial_time=100.0)
    # aging_rate = 1 priority point per second
    pq = PriorityQueue(max_capacity=100, aging_rate=1.0, clock=clk)

    # Low-priority request (priority=1) arrives at T=100
    r_low = InferenceRequest(request_id="low_priority_req", model_name="gpt-2", prompt="p", max_tokens=10, priority=1, arrival_time=clk.now())
    pq.enqueue(r_low)

    # High-priority request (priority=10) arrives immediately at T=100
    r_high1 = InferenceRequest(request_id="high_1", model_name="gpt-2", prompt="p", max_tokens=10, priority=10, arrival_time=clk.now())
    pq.enqueue(r_high1)

    # At T=100: high_1 has priority 10 vs low's 1. high_1 dequeues first.
    first = pq.dequeue()
    assert first.request_id == "high_1"

    # Now simulate time advancement by 15 seconds without serving low_priority_req
    clk.advance(15.0)  # Clock is now 115.0

    # A brand new high-priority request (priority=10) arrives at T=115
    r_high2 = InferenceRequest(request_id="high_2", model_name="gpt-2", prompt="p", max_tokens=10, priority=10, arrival_time=clk.now())
    pq.enqueue(r_high2)

    # Low-priority request has aged: 1 + 15*1.0 = 16 > 10 (r_high2)
    # Therefore, starvation is strictly prevented and low_priority_req is dequeued next!
    next_req = pq.dequeue()
    assert next_req.request_id == "low_priority_req"
    assert next_req.effective_priority == 16.0

    # Finally high_2 is dequeued
    last_req = pq.dequeue()
    assert last_req.request_id == "high_2"
