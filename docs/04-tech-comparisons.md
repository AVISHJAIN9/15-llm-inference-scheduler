# Technology Choices & Exhaustive Comparisons

## Serving Engine Architecture: Custom Scheduler vs vLLM vs TGI vs TensorRT-LLM

| Factor | Custom Scheduler [This Project] | vLLM | HuggingFace TGI | TensorRT-LLM |
| :--- | :--- | :--- | :--- | :--- |
| **KV Cache Management** | **Paged KV-Cache (Virtual Memory)** | PagedAttention | Paged Attention | Paged KV Cache |
| **Batching Mechanism** | **Iteration-Level Continuous** | Iteration-Level Continuous | Continuous Batching | In-Flight Batching |
| **Inspectability & Control** | **100% Transparent Python Control Plane**| Complex C++/CUDA Kernels | Rust Core + Python | Highly Proprietary C++ |
| **Portability** | **Runs on CPU & GPU (Simulated/Real)** | GPU Only (CUDA/ROCm) | GPU Centric | NVIDIA CUDA Only |

- **Why This Architecture**: Designed as a pure, inspectable systems control plane that models and executes the complex state machines of continuous batching, memory page allocation, and multi-replica routing with 99 verified automated unit tests. [CONFIRM WITH DEVELOPER]
