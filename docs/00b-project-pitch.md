# Project Pitch: LLM Serving Inference Scheduler

## 30-Second Elevator Pitch
> "I built an iteration-level LLM inference scheduler and control plane inspired by vLLM and Orca. Traditional request-level batching causes severe GPU underutilization because short requests must wait for long requests to finish generating tokens. My scheduler implements continuous batching, dynamically inserting new prompts at each forward pass, and pairs it with a paged KV-cache memory allocator that treats GPU memory like virtual memory pages. This cuts KV memory fragmentation by over 90% and delivers high-throughput token streaming with low time-to-first-token."

---

## 2-Minute Technical Interview Pitch
> "Serving Large Language Models in production presents two critical systems challenges: memory fragmentation in the Key-Value (KV) cache and severe GPU compute starvation under dynamic sequence lengths.
>
> In naive static batching, requests of varying lengths are padded together. The GPU remains locked until the longest request completes, wasting over 60% of GPU compute and leaving memory unusable.
>
> To solve this, I designed and built **15-LLM-Inference-Scheduler**, a continuous-batching serving engine and multi-worker control plane.
>
> First, I implemented iteration-level continuous batching in `backend/src/batching/continuous.py`. Rather than waiting for a whole batch to finish, the scheduler executes a single autoregressive decoding step for active sequences, evicts completed sequences immediately, and injects newly arrived prompts into the very next iteration.
>
> Second, to manage the explosive memory demands of self-attention, I implemented a Paged KV-Cache allocator in `backend/src/kv/paged.py`. Modeled directly after OS virtual memory paging, physical KV cache memory is sliced into small fixed-size blocks (16 tokens each). Logical request tokens map to physical blocks through a page table, completely eliminating external memory fragmentation and allowing multiple concurrent sequences to share prefill prefixes.
>
> Third, I decoupled compute-heavy prompt prefill from memory-bandwidth-bound token decoding using a chunked prefill scheduler, maintaining smooth inter-token latency (ITL) under heavy prompt arrival bursts.
>
> The control plane exposes standard REST and Server-Sent Events (SSE) streaming APIs in FastAPI, routed to a pool of GPU worker replicas with health tracking. The frontend is built in React and TypeScript, visualizing active queue states and latency percentiles. The backend is validated by 99 automated pytest tests covering admission rejection, prefill preemption, and memory page reclamation."
