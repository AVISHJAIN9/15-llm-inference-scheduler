# Security & Resource Quotas

- **Prompt Length Caps**: Max context length strictly enforced by admission controller (prevents memory allocation exhaustion attacks).
- **Token Bucket Rate Limiting**: Per-API-key token generation rate limiters.
- **Model Whitelisting**: Rejects requests targeting un-registered or un-verified model weights.
