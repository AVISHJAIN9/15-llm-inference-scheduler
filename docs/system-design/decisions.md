# Architecture Decision Records (ADR Log)

## Technical Specification & Deep Dive
Formal architectural trade-offs: Continuous Batching, Paged KV-Cache, and FastAPI control plane.

```mermaid
flowchart LR
    Scheduler[Continuous Batcher] --> VRAM[GPU Memory Paged KV]
    VRAM --> Execution[Autoregressive Step]
```
