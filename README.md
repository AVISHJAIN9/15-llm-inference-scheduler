# 15-llm-inference-scheduler

## Mission
MVP implementation for 15-llm-inference-scheduler.

## Status
<!-- STATUS:BEGIN -->
**COMPLETED 90 · WORKING 0 · TODO 0**

### Area Scheduler Core (14 features · 14 COMPLETED · 0 WORKING · 0 TODO)

| ID | Feature | Layers | Status |
|---|---|---|---|
| SCH-002 | Request admission | BE | COMPLETED |
| SCH-003 | Queue management | BE | COMPLETED |
| SCH-005 | FIFO queue | BE | COMPLETED |
| SCH-006 | Priority queue | BE | COMPLETED |
| SCH-007 | Weighted fair queue | BE | COMPLETED |
| SCH-011 | Queue aging | BE | COMPLETED |
| SCH-012 | Backpressure | BE | COMPLETED |
| SCH-014 | Request cancellation | BE | COMPLETED |
| SCH-001 | Scheduler policy model | BE | COMPLETED |
| SCH-004 | Priority classes | BE | COMPLETED |
| SCH-008 | Deadline-aware scheduling | BE | COMPLETED |
| SCH-009 | Tenant-aware scheduling | BE | COMPLETED |
| SCH-010 | Per-model queues | BE | COMPLETED |
| SCH-013 | Admission rejection | BE | COMPLETED |

### Area GPU / Accelerator Management (6 features · 6 COMPLETED · 0 WORKING · 0 TODO)

| ID | Feature | Layers | Status |
|---|---|---|---|
| SCH-015 | GPU inventory | BE+DB | COMPLETED |
| SCH-017 | GPU memory tracking | BE+DB | COMPLETED |
| SCH-024 | Memory admission control | BE+DB | COMPLETED |
| SCH-016 | GPU health detection | BE+DB | COMPLETED |
| SCH-018 | GPU utilization tracking | BE+DB | COMPLETED |
| SCH-020 | Device assignment | BE+DB | COMPLETED |

### Area Model & Runtime Management (5 features · 5 COMPLETED · 0 WORKING · 0 TODO)

| ID | Feature | Layers | Status |
|---|---|---|---|
| SCH-029 | Model registry | BE+DB | COMPLETED |
| SCH-030 | Model metadata | BE+DB | COMPLETED |
| SCH-033 | Model loading | BE+DB | COMPLETED |
| SCH-038 | Model memory footprint | BE+DB | COMPLETED |
| SCH-042 | Runtime selection | BE+DB | COMPLETED |

### Area KV Cache & Memory (13 features · 13 COMPLETED · 0 WORKING · 0 TODO)

| ID | Feature | Layers | Status |
|---|---|---|---|
| SCH-043 | KV-cache manager | BE+DB | COMPLETED |
| SCH-045 | KV-cache allocation | BE+DB | COMPLETED |
| SCH-046 | KV-cache reclamation | BE+DB | COMPLETED |
| SCH-048 | Prefix caching | BE+DB | COMPLETED |
| SCH-049 | Paged KV cache | BE+DB | COMPLETED |
| SCH-052 | OOM prevention | BE+DB | COMPLETED |
| SCH-053 | KV-cache eviction policy | BE+DB | COMPLETED |
| SCH-044 | KV-cache capacity tracking | BE+DB | COMPLETED |
| SCH-047 | KV-cache reuse | BE+DB | COMPLETED |
| SCH-051 | Memory pressure detection | BE+DB | COMPLETED |
| SCH-054 | Per-request cache budget | BE+DB | COMPLETED |
| SCH-055 | Tenant cache quotas | BE+DB | COMPLETED |
| SCH-056 | Cache hit-rate metrics | BE+DB | COMPLETED |

### Area Batching & Throughput (8 features · 8 COMPLETED · 0 WORKING · 0 TODO)

| ID | Feature | Layers | Status |
|---|---|---|---|
| SCH-057 | Continuous batching | BE | COMPLETED |
| SCH-061 | Max batch size | BE | COMPLETED |
| SCH-062 | Token-budget batching | BE | COMPLETED |
| SCH-065 | Mixed prefill/decode batching | BE | COMPLETED |
| SCH-058 | Dynamic batching | BE | COMPLETED |
| SCH-060 | Batch formation window | BE | COMPLETED |
| SCH-063 | Prefill batching | BE | COMPLETED |
| SCH-064 | Decode batching | BE | COMPLETED |

### Area Request Routing & Load Balancing (8 features · 8 COMPLETED · 0 WORKING · 0 TODO)

| ID | Feature | Layers | Status |
|---|---|---|---|
| SCH-071 | Model-aware routing | BE | COMPLETED |
| SCH-073 | Least-loaded routing | BE | COMPLETED |
| SCH-083 | Replica draining | BE | COMPLETED |
| SCH-072 | GPU-aware routing | BE | COMPLETED |
| SCH-074 | Queue-length routing | BE | COMPLETED |
| SCH-075 | Latency-aware routing | BE | COMPLETED |
| SCH-082 | Replica health checks | BE | COMPLETED |
| SCH-084 | Replica failover | BE | COMPLETED |

### Area Distributed Coordination (12 features · 12 COMPLETED · 0 WORKING · 0 TODO)

| ID | Feature | Layers | Status |
|---|---|---|---|
| SCH-085 | Scheduler leader election | BE | COMPLETED |
| SCH-089 | Lease management | BE | COMPLETED |
| SCH-090 | Worker registration | BE | COMPLETED |
| SCH-091 | Worker heartbeats | BE | COMPLETED |
| SCH-096 | Exactly-once dispatch semantics | BE | COMPLETED |
| SCH-097 | At-least-once recovery | BE | COMPLETED |
| SCH-098 | Duplicate dispatch prevention | BE | COMPLETED |
| SCH-086 | Distributed scheduler state | BE | COMPLETED |
| SCH-087 | Shared queue coordination | BE | COMPLETED |
| SCH-092 | Worker discovery | BE | COMPLETED |
| SCH-094 | Scheduler failover | BE | COMPLETED |
| SCH-095 | State recovery | BE | COMPLETED |

### Area Backend APIs & Control Plane (8 features · 8 COMPLETED · 0 WORKING · 0 TODO)

| ID | Feature | Layers | Status |
|---|---|---|---|
| SCH-099 | Inference request API | BE | COMPLETED |
| SCH-100 | Streaming inference API | BE | COMPLETED |
| SCH-102 | Scheduler API | BE | COMPLETED |
| SCH-103 | Queue API | BE | COMPLETED |
| SCH-105 | Worker API | BE | COMPLETED |
| SCH-107 | Health endpoint | BE | COMPLETED |
| SCH-108 | Readiness endpoint | BE | COMPLETED |
| SCH-109 | Metrics endpoint | BE | COMPLETED |

### Area Observability & Reliability (8 features · 8 COMPLETED · 0 WORKING · 0 TODO)

| ID | Feature | Layers | Status |
|---|---|---|---|
| SCH-112 | Prometheus metrics | BE | COMPLETED |
| SCH-117 | TTFT metrics | BE | COMPLETED |
| SCH-118 | TPOT metrics | BE | COMPLETED |
| SCH-113 | OpenTelemetry tracing | BE | COMPLETED |
| SCH-114 | Structured logs | BE | COMPLETED |
| SCH-115 | Request decision logs | BE | COMPLETED |
| SCH-116 | Queue wait-time metrics | BE | COMPLETED |
| SCH-119 | End-to-end latency metrics | BE | COMPLETED |

### Area Frontend / Operations Console (5 features · 5 COMPLETED · 0 WORKING · 0 TODO)

| ID | Feature | Layers | Status |
|---|---|---|---|
| SCH-138 | Scheduler dashboard | FE+BE | COMPLETED |
| SCH-139 | Queue dashboard | FE+BE | COMPLETED |
| SCH-143 | Live request view | FE+BE | COMPLETED |
| SCH-144 | Request detail page | FE+BE | COMPLETED |
| SCH-146 | Latency charts | FE+BE | COMPLETED |

### Area Security & AI/ML Optimization (3 features · 3 COMPLETED · 0 WORKING · 0 TODO)

| ID | Feature | Layers | Status |
|---|---|---|---|
| SCH-125 | API-key authentication | BE | COMPLETED |
| SCH-128 | Tenant isolation | BE | COMPLETED |
| SCH-130 | Rate limiting | BE | COMPLETED |

<!-- STATUS:END -->

## Architecture
Production-grade distributed system implementation.

## How to run
```bash
make up
make test
```

## Decisions

- SCH-096: Physical exactly-once across distributed networks is impossible under partitions; implemented at-least-once recovery combined with fencing-tokened deduplication dispatch = effectively-once delivery.
## Benchmarks

## Limitations
- SCH-015, SCH-017, SCH-024: GPU inventory and VRAM tracking use SIMULATED_HW; upgrade requires physical NVIDIA GPU with NVML/CUDA
