# Full Project Analysis: LLM Inference Scheduler

## System Trace & Component Interaction

```mermaid
sequenceDiagram
    autonumber
    actor Client
    participant API as api/app.py
    participant Queue as scheduler/queue.py
    participant Batcher as batching/continuous.py
    participant KV as kv/paged.py
    participant Worker as GPU Worker

    Client->>API: POST /v1/chat/completions/stream
    API->>Queue: push(InferenceRequest)
    loop Every Autoregressive Step
        Batcher->>Queue: pop_eligible_requests()
        Batcher->>KV: allocate_pages(active_requests)
        Batcher->>Worker: execute_forward_step(batch)
        Worker-->>Batcher: new_tokens
        Batcher-->>API: yield tokens (SSE)
        API-->>Client: data: {"token": "..."}
    end
```

### Final Baseline Inventory Counts
- **Total Backend Python Modules**: 22 modules across `scheduler/`, `batching/`, `kv/`, `coordination/`
- **Total Passing Automated Tests**: 99 tests (`backend/tests/`)
- **Total Frontend Dashboard Components**: 5 React components (`frontend/src/`)
