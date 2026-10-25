# AI Architecture & Model Serving

- **Pre-trained Models Supported**: Qwen 2.5, Llama 3, GPT-2.
- **Zero Custom Training**: This platform is a serving and scheduling system for pre-trained weights; no custom model was trained.
- **Prefill vs Decode Decoupling**: Compute-bound GEMM operations for prefill are scheduled in chunks to protect decode memory bandwidth.
