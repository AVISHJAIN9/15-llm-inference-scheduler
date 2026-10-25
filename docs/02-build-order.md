# Step-by-Step Build Order

1. **Request Schemas & Token Data Structures**: Implement `backend/src/models/` defining prompt, generation params, and token statuses.
2. **Admission Controller & FIFO Queue**: Build `scheduler/admission.py` and `scheduler/queue.py` with capacity limits.
3. **Paged KV Cache Allocator**: Implement `kv/paged.py` block manager and logical-to-physical page table mapper.
4. **Continuous Batching Iteration Loop**: Construct `batching/continuous.py` interleaving prefill slices and decode steps.
5. **Worker Registry & Router**: Implement `coordination/workers.py` and `routing/router.py`.
6. **FastAPI REST & SSE Streaming**: Wire endpoints in `api/app.py` with streaming async generators.
7. **React Real-Time Telemetry Dashboard**: Build `frontend/src/` visualizing active queues and latency metrics.
