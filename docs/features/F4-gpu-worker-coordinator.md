# F4: GPU Worker Registry & Multi-Replica Routing

## Technical Specification
Tracks worker heartbeats, GPU memory pressure, and routes requests.

---

## Architecture & Flow

```mermaid
flowchart LR
    Client[Client Request] --> Queue[Admission Queue]
    Queue --> Batcher[Continuous Batcher]
    Batcher --> Allocator[Paged KV Allocator]
    Allocator --> Worker[GPU Forward Step]
    Worker --> Stream[SSE Token Stream]
```

### Edge Cases Handled
- **KV Cache Exhaustion**: In-flight requests are gracefully preempted or swapped to host memory rather than crashing.
- **Worker Timeout**: Worker heartbeats expire after 5 seconds of silence, automatically re-routing requests to healthy replicas.

---

## Say It Out Loud
> "For this feature, I prioritized GPU hardware efficiency and predictable user latency. By decoupling token generation into atomic iterations, the scheduler achieves maximum throughput while upholding strict latency SLAs."
