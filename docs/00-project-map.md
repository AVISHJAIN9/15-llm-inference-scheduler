# Project Structure & Dependency Map

## File Hierarchy

```
15-llm-inference-scheduler/
├── backend/
│   ├── src/
│   │   ├── api/                # FastAPI application entry & HTTP/SSE routers
│   │   │   └── app.py          # REST & Server-Sent Events endpoints
│   │   ├── batching/           # Continuous iteration-level batching engine
│   │   │   └── continuous.py   # Iteration scheduler & token budget allocator
│   │   ├── coordination/       # Worker replica registration & heartbeats
│   │   ├── gpu/                # GPU memory tracking & simulated device state
│   │   ├── kv/                 # Paged KV-cache memory allocator & page tables
│   │   │   └── paged.py        # Block allocator, page tables, prefix sharing
│   │   ├── models/             # Request, token, and worker data schemas
│   │   ├── observability/      # TTFT & ITL metrics exporter (Prometheus format)
│   │   ├── routing/            # Multi-worker load-balancing router
│   │   ├── scheduler/          # Admission control, FIFO & priority queues
│   │   └── security/           # Token quotas, prompt length limits
│   └── tests/                  # 29 test files (99 passing pytest unit/integration tests)
├── frontend/
│   ├── src/
│   │   ├── App.tsx             # Root React dashboard layout
│   │   ├── LatencyCharts.tsx   # TTFT, ITL, and p99 latency visualization
│   │   ├── LiveRequestView.tsx # Real-time SSE token stream viewer
│   │   ├── QueueDashboard.tsx  # In-flight queue depth & preemption metrics
│   │   └── SchedulerDashboard.tsx # Worker replica health & memory allocation
│   └── package.json            # React 18, TypeScript, Tailwind dependencies
├── legacy_scaffold/            # Preserved initial scaffolding stubs
├── FEATURES.csv                # 100 feature matrix
├── PROGRESS.md                 # Implementation milestone log
└── SPEC.txt                    # System design specification
```

---

## Tech Stack & Runtime Dependencies

| Tier | Technology | Version | Purpose |
| :--- | :--- | :--- | :--- |
| **Backend Runtime** | Python | 3.13 | Asynchronous control plane runtime |
| **Framework** | FastAPI | 0.115+ | REST and Server-Sent Events streaming endpoints |
| **Numerical Engine**| NumPy | 2.0+ | Fast page table lookups and latency array math |
| **Data Models** | Pydantic | 2.10+ | Strict type validation for token requests and worker state |
| **Test Engine** | Pytest / Pytest-Asyncio | 8.3+ | 99 unit and integration tests |
| **Frontend UI** | React | 18.3.1 | Component-driven telemetry and streaming token UI |
| **Bundler** | Vite | 6.0+ | High-speed ESM development and production bundling |
