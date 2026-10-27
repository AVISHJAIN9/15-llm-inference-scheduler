# Deployment Guide: LLM Continuous Batching Control Plane

## Hosting & Infrastructure
- **Live URL**: [https://aj-llm-inference-scheduler.onrender.com/healthz](https://aj-llm-inference-scheduler.onrender.com/healthz)
- **Hosting Environment**: Render Free-Tier PaaS

*Note on Cold Starts: Free-tier Render instances spin down after 15 minutes of inactivity. Initial inbound requests may experience a 30-50 second cold-start delay while the container boots.*

## Containerization
A `Dockerfile` is provided for containerized multi-stage builds.
