# Project Type Detection & Adaptation Track

## Step 0 Pre-Check: Architecture & Track Classification

This document records the formal codebase inspection and classification of `15-llm-inference-scheduler`.

---

### Detection Evidence

A comprehensive inspection of the repository `/Users/avishjain/avishjain9-repos/15-llm-inference-scheduler` was conducted:

| Artifact Checked | Findings / Content | Classification Evidence |
| :--- | :--- | :--- |
| **Directory Name** | `15-llm-inference-scheduler` | High-performance LLM serving control plane & continuous batching scheduler. |
| **Backend Code** | `backend/src/scheduler/`, `backend/src/batching/`, `backend/src/kv/` | Python 3.13, FastAPI, NumPy, Paged KV-Cache allocator, FIFO & priority queues. |
| **Frontend Code** | `frontend/src/` (`App.tsx`, `SchedulerDashboard.tsx`, `LiveRequestView.tsx`) | React 18, TypeScript, Tailwind CSS, real-time token throughput & latency visualizers. |
| **Test Suite** | `backend/tests/` (29 test files) | 99 passing unit & integration tests running via `pytest`. |

---

### Formal Classification
- **Primary Classification**: **Track C & A (Backend / Systems Infrastructure & AI Serving Control Plane)**
- **Sub-tracks**:
  - High-performance asynchronous control plane (FastAPI, asyncio)
  - Operating system memory management simulation (Paged KV-cache virtual memory allocator)
  - Real-time token streaming frontend (React, Server-Sent Events, telemetry charts)

---

### Adaptation Rules for This Project
1. **Backend Focus**: Emphasize continuous iteration-level batching (Orca paradigm), chunked prefill scheduling, KV-cache fragmentation elimination, and GPU worker routing.
2. **Frontend Focus**: Detail SSE live request streams, queue depth monitoring, time-to-first-token (TTFT), and inter-token latency (ITL) charts.
3. **AI Focus**: Explicitly note that no custom model weights were trained; the system is an infrastructure serving scheduler for pre-trained LLMs (Llama-3, Qwen, GPT-2).
