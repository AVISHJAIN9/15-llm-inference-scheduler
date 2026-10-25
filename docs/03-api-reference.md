# Complete API Reference

### 1. Synchronous Inference Request
- **Method**: `POST`
- **Path**: `/v1/chat/completions`
- **Body**:
```json
{
  "model_name": "qwen2.5-0.5b",
  "prompt": "Explain the CAP theorem in distributed systems.",
  "max_tokens": 128,
  "temperature": 0.7
}
```
- **Response**: `200 OK` with completed generated text and token statistics.

### 2. Streaming Inference Request (SSE)
- **Method**: `POST`
- **Path**: `/v1/chat/completions/stream`
- **Headers**: `Accept: text/event-stream`
- **Response**: Chunked SSE stream yielding `data: {"token": "...", "finish_reason": null}`.

### 3. Worker Status & Cluster Health
- **Method**: `GET`
- **Path**: `/healthz`
- **Response**: `200 OK` with replica count, active batch sizes, and KV cache utilization.
