import pytest
from scheduler.models import InferenceRequest
from scheduler.model_queues import ModelQueueManager, WorkerModelCapability

def test_SCH_010_per_model_queues():
    """
    SCH-010: Per-model queues.
    Ensures dedicated per-model queuing and guarantees that a request NEVER runs on
    a worker lacking the requested model.
    """
    mqm = ModelQueueManager()

    # Enqueue requests for different models
    req_llama_1 = InferenceRequest(request_id="l1", model_name="llama-3-8b", prompt="p1", arrival_time=1.0)
    req_llama_2 = InferenceRequest(request_id="l2", model_name="llama-3-8b", prompt="p2", arrival_time=2.0)
    req_mistral_1 = InferenceRequest(request_id="m1", model_name="mistral-7b", prompt="p3", arrival_time=3.0)
    req_deepseek_1 = InferenceRequest(request_id="d1", model_name="deepseek-coder", prompt="p4", arrival_time=4.0)

    mqm.enqueue(req_llama_1)
    mqm.enqueue(req_llama_2)
    mqm.enqueue(req_mistral_1)
    mqm.enqueue(req_deepseek_1)

    assert mqm.get_queue_depth("llama-3-8b") == 2
    assert mqm.get_queue_depth("mistral-7b") == 1
    assert mqm.get_queue_depth("deepseek-coder") == 1
    assert mqm.get_queue_depth("nonexistent-model") == 0

    # Worker 1 only has 'mistral-7b' loaded
    w1 = WorkerModelCapability(worker_id="w-mistral", loaded_models=["mistral-7b"])
    popped_w1 = mqm.dispatch_for_worker(w1)
    assert popped_w1 is not None
    assert popped_w1.request_id == "m1"
    assert popped_w1.model_name == "mistral-7b"
    assert mqm.get_queue_depth("mistral-7b") == 0

    # If w1 tries to pull again, returns None (no more mistral requests, even though llama requests exist!)
    assert mqm.dispatch_for_worker(w1) is None

    # Worker 2 has 'llama-3-8b' loaded
    w2 = WorkerModelCapability(worker_id="w-llama", loaded_models=["llama-3-8b"])
    popped_w2 = mqm.dispatch_for_worker(w2)
    assert popped_w2 is not None
    assert popped_w2.request_id == "l1"
    assert popped_w2.model_name == "llama-3-8b"
    assert mqm.get_queue_depth("llama-3-8b") == 1

    # Worker 3 has NO matching models loaded
    w3 = WorkerModelCapability(worker_id="w-empty", loaded_models=["phi-3"])
    assert mqm.dispatch_for_worker(w3) is None
