# Technical Glossary

- **Continuous Batching**: Iteration-level scheduling that modifies batch membership at every forward token step.
- **KV Cache**: Cached Key and Value attention tensors stored in GPU memory to avoid recomputing past tokens.
- **TTFT**: Time-to-First-Token.
- **ITL**: Inter-Token Latency.
- **PagedAttention**: Memory allocation algorithm mapping sequence token ranges to non-contiguous physical memory blocks.
