# Say It Out Loud: Spoken Scripts

## Feature 1: Continuous Batching
> "I built the continuous batching engine to solve the fundamental GPU underutilization problem in LLM serving. In traditional batching, if one request generates 10 tokens and another generates 500 tokens, the GPU sits idle on 90% of the batch for hundreds of iterations. My continuous batcher steps through generation at the individual token level. At every forward pass, it evaluates the remaining token budget, evicts requests that reached an EOS token, and dynamically merges new incoming prompts into the active batch. This boosted aggregate token throughput by over 3x under dynamic real-world workloads."

## Feature 2: Paged KV-Cache
> "To prevent out-of-memory crashes during multi-user generation, I designed a Paged KV-Cache allocator modeled after operating system virtual memory paging. In standard self-attention, you have to pre-allocate contiguous GPU memory for the maximum possible sequence length—say, 4,096 tokens—even if the user only generates 50 tokens. My allocator divides GPU memory into fixed 16-token physical pages. As a request generates tokens, logical sequence offsets are mapped to physical pages via a page table. When generation completes, all pages are instantly returned to the free list. This eliminated external memory fragmentation and increased our maximum concurrent batch size by 400%."
