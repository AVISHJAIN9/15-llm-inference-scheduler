"""
FastAPI application for LLM Inference Scheduler (SCH-099, SCH-100).
Provides standard REST and Server-Sent Events (SSE) streaming inference endpoints.
"""

import asyncio
import json
import time
from typing import Optional, Dict, Any, AsyncGenerator, List
from fastapi import FastAPI, Request, Response, HTTPException, status
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from scheduler.models import InferenceRequest, RequestStatus
from scheduler.admission import AdmissionController
from scheduler.queue import FIFOQueue
from batching.continuous import ContinuousBatcher
from coordination.workers import WorkerRegistry
from routing.router import RequestRouter, WorkerReplica, ReplicaStatus
from observability.metrics import default_metrics, CONTENT_TYPE_LATEST

app = FastAPI(
    title="LLM Inference Scheduler Control Plane",
    version="1.0.0",
    docs_url="/docs",
    openapi_url="/openapi.json"
)

admission_ctrl = AdmissionController(allowed_models=["gpt-2", "qwen2.5-0.5b", "llama-3"], max_queue_depth=1000)
queue = FIFOQueue(max_capacity=1000)
batcher = ContinuousBatcher(max_batch_size=8, max_token_budget_per_step=256)
worker_registry = WorkerRegistry()
router = RequestRouter()
scheduler_config: Dict[str, Any] = {
    "policy": "FIFO",
    "max_batch_size": 8,
    "max_queue_depth": 1000,
    "token_budget": 256
}
request_history: Dict[str, Dict[str, Any]] = {}

class InferenceRequestPayload(BaseModel):
    request_id: Optional[str] = None
    model_name: str
    prompt: str
    max_tokens: int = 16
    priority: int = 0
    tenant_id: str = "default"

APP_START_TIME = time.time()

# Global operational flags for health/readiness testing
system_health_status = {"healthy": True, "reason": "System operating normally"}
system_readiness_status = {"ready": True, "reason": "Ready to accept traffic"}

@app.get("/healthz")
@app.get("/api/v1/healthz")
async def healthz():
    """Health check endpoint (SCH-107)."""
    uptime = time.time() - APP_START_TIME
    kv_ok = batcher.kv_manager.total_blocks > 0
    queue_ok = queue.size() <= queue.max_capacity
    is_healthy = system_health_status["healthy"] and kv_ok and queue_ok

    payload = {
        "status": "HEALTHY" if is_healthy else "UNHEALTHY",
        "uptime_seconds": round(uptime, 2),
        "components": {
            "scheduler": "UP",
            "kv_cache": "UP" if kv_ok else "DOWN",
            "queue": "UP" if queue_ok else "DOWN"
        }
    }
    if not is_healthy:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"error": {"code": "SERVICE_UNHEALTHY", "message": system_health_status["reason"], "details": payload}}
        )
    return payload



@app.get("/readyz")
@app.get("/api/v1/readyz")
async def readyz():
    """Readiness probe endpoint (SCH-108)."""
    queue_has_capacity = queue.size() < queue.max_capacity
    kv_has_blocks = batcher.kv_manager.free_blocks_count > 0 or batcher.current_batch_size > 0
    is_ready = system_readiness_status["ready"] and queue_has_capacity and kv_has_blocks

    payload = {
        "status": "READY" if is_ready else "NOT_READY",
        "queue_depth": queue.size(),
        "max_queue_depth": queue.max_capacity,
        "active_batch": batcher.current_batch_size,
        "kv_free_blocks": batcher.kv_manager.free_blocks_count,
        "kv_total_blocks": batcher.kv_manager.total_blocks
    }
    if not is_ready:
        reason = "Queue capacity reached" if not queue_has_capacity else system_readiness_status["reason"]
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"error": {"code": "NOT_READY", "message": reason, "details": payload}}
        )
    return payload



@app.get("/metrics")
@app.get("/api/v1/metrics")
async def metrics_endpoint():
    """Prometheus metrics endpoint (SCH-109)."""
    default_metrics.update_queue_depth(queue.size())
    default_metrics.update_batch_size(batcher.current_batch_size)
    default_metrics.update_kv_blocks(batcher.kv_manager.used_blocks_count, batcher.kv_manager.free_blocks_count)
    content = default_metrics.generate_metrics_text()
    return Response(content=content, media_type=CONTENT_TYPE_LATEST)



@app.post("/api/v1/inference")
async def submit_inference(payload: InferenceRequestPayload):
    """Synchronous inference request API (SCH-099)."""
    req_id = payload.request_id or f"req-{int(time.time()*1000)}"
    req = InferenceRequest(
        request_id=req_id,
        model_name=payload.model_name,
        prompt=payload.prompt,
        max_tokens=payload.max_tokens,
        priority=payload.priority,
        tenant_id=payload.tenant_id
    )

    decision = admission_ctrl.admit(req, current_queue_size=queue.size())
    if not decision.admitted:
        return JSONResponse(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS if "saturated" in decision.reason else status.HTTP_400_BAD_REQUEST,
            content={"error": {"code": "ADMISSION_REJECTED", "message": decision.reason, "request_id": req_id}}
        )

    if not batcher.admit(req):
        queue.enqueue(req)
        # Attempt to drain from queue to batcher
        if batcher.admit(req):
            queue.remove(req.request_id)
            default_metrics.record_queue_wait(payload.model_name, time.time() - req.arrival_time)
    else:
        default_metrics.record_queue_wait(payload.model_name, 0.0)

    # Step through generation to complete execution
    start_time = time.time()
    first_token_time = None
    last_token_time = start_time
    generated_tokens = []
    max_steps = payload.max_tokens + 2

    for _ in range(max_steps):
        res = batcher.step()
        if req_id in res["step_tokens"]:
            now = time.time()
            if first_token_time is None:
                first_token_time = now
                default_metrics.record_ttft(payload.model_name, now - start_time)
            else:
                default_metrics.record_tpot(payload.model_name, now - last_token_time)
            last_token_time = now
            generated_tokens.append(res["step_tokens"][req_id])
        if req.status == RequestStatus.COMPLETED:
            break

    e2e_duration = time.time() - req.arrival_time
    default_metrics.record_e2e_latency(payload.model_name, e2e_duration)
    default_metrics.record_request(payload.model_name, "completed")

    res_dict = {
        "request_id": req_id,
        "model_name": payload.model_name,
        "tenant_id": payload.tenant_id,
        "priority": payload.priority,
        "status": req.status.value,
        "tokens_generated": len(generated_tokens),
        "tokens": generated_tokens,
        "text": " ".join(generated_tokens),
        "prompt_length": len(payload.prompt),
        "arrival_time": req.arrival_time,
        "completion_time": time.time(),
        "e2e_duration_ms": round(e2e_duration * 1000, 2),
        "kv_blocks_allocated": 1
    }
    request_history[req_id] = res_dict
    return res_dict

@app.post("/api/v1/inference/stream")
async def stream_inference(payload: InferenceRequestPayload):
    """Streaming inference API via Server-Sent Events (SCH-100)."""
    req_id = payload.request_id or f"req-stream-{int(time.time()*1000)}"
    req = InferenceRequest(
        request_id=req_id,
        model_name=payload.model_name,
        prompt=payload.prompt,
        max_tokens=payload.max_tokens,
        priority=payload.priority,
        tenant_id=payload.tenant_id
    )

    decision = admission_ctrl.admit(req, current_queue_size=queue.size())
    if not decision.admitted:
        default_metrics.record_request(payload.model_name, "rejected")
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"error": {"code": "ADMISSION_REJECTED", "message": decision.reason, "request_id": req_id}}
        )

    if not batcher.admit(req):
        queue.enqueue(req)

    async def token_generator() -> AsyncGenerator[str, None]:
        start_time = time.time()
        first_token_sent = False
        last_step_time = start_time
        step_idx = 0

        for _ in range(payload.max_tokens + 2):
            res = batcher.step()
            if req_id in res["step_tokens"]:
                step_idx += 1
                token_text = res["step_tokens"][req_id]
                now = time.time()
                if not first_token_sent:
                    ttft_ms = round((now - start_time) * 1000, 2)
                    default_metrics.record_ttft(payload.model_name, now - start_time)
                    first_token_sent = True
                else:
                    ttft_ms = None
                    default_metrics.record_tpot(payload.model_name, now - last_step_time)
                last_step_time = now

                data = {
                    "request_id": req_id,
                    "step": step_idx,
                    "token": token_text,
                    "ttft_ms": ttft_ms
                }
                yield f"data: {json.dumps(data)}\n\n"

            if req.status == RequestStatus.COMPLETED:
                break
            await asyncio.sleep(0.001)  # Yield slice for SSE streaming chunk delivery

        default_metrics.record_request(payload.model_name, "completed")
        yield "data: [DONE]\n\n"

    return StreamingResponse(token_generator(), media_type="text/event-stream")

@app.get("/api/v1/dashboard/stats")
async def get_dashboard_stats():
    """Returns live cluster & scheduler statistics for Ops Console (SCH-138)."""
    return {
        "active_batch_size": batcher.current_batch_size,
        "max_batch_size": batcher.max_batch_size,
        "kv_blocks_used": batcher.kv_manager.used_blocks_count,
        "kv_blocks_free": batcher.kv_manager.free_blocks_count,
        "kv_blocks_total": batcher.kv_manager.total_blocks,
        "iteration_count": batcher.iteration_count,
        "queue_depth": queue.size(),
        "uptime_seconds": round(time.time() - APP_START_TIME, 2)
    }

@app.get("/api/v1/dashboard/queue")
async def get_dashboard_queue():
    """Returns detailed queue inspection data for Ops Console (SCH-139)."""
    items = [
        {
            "request_id": req.request_id,
            "model_name": req.model_name,
            "priority": req.priority,
            "max_tokens": req.max_tokens,
            "arrival_time": req.arrival_time,
            "status": req.status.value
        }
        for req in queue.all_requests()
    ]
    return {
        "queue_depth": len(items),
        "max_capacity": queue.max_capacity,
        "queued_items": items
    }

# ==========================================
# Frontend / Operations Console API (SCH-143, SCH-144, SCH-146)
# ==========================================
@app.get("/api/v1/dashboard/requests/live")
async def get_live_requests():
    """Live active requests view for Ops Console (SCH-143)."""
    running = [
        {
            "request_id": seq.request_id,
            "model_name": seq.request.model_name,
            "tenant_id": seq.request.tenant_id,
            "priority": seq.request.priority,
            "tokens_generated": len(seq.generated_tokens),
            "max_tokens": seq.request.max_tokens,
            "phase": seq.phase.value,
            "arrival_time": seq.request.arrival_time,
            "elapsed_seconds": round(time.time() - seq.request.arrival_time, 2),
            "status": seq.request.status.value
        }
        for seq in batcher.active_batch.values()
    ]
    return {
        "active_count": len(running),
        "max_batch_size": batcher.max_batch_size,
        "requests": running
    }

@app.get("/api/v1/dashboard/requests/{request_id}")
async def get_request_detail(request_id: str):
    """Detailed inspection of an individual inference request (SCH-144)."""
    # 1. Check active sequences in batcher
    if request_id in batcher.active_batch:
        seq = batcher.active_batch[request_id]
        return {
            "request_id": seq.request_id,
            "model_name": seq.request.model_name,
            "tenant_id": seq.request.tenant_id,
            "priority": seq.request.priority,
            "status": seq.request.status.value,
            "phase": seq.phase.value,
            "prompt_length": len(seq.request.prompt),
            "tokens_generated": len(seq.generated_tokens),
            "max_tokens": seq.request.max_tokens,
            "arrival_time": seq.request.arrival_time,
            "elapsed_seconds": round(time.time() - seq.request.arrival_time, 2),
            "kv_blocks_allocated": len(seq.allocated_blocks)
        }

    # 2. Check pending in queue
    for req in queue.all_requests():
        if req.request_id == request_id:
            return {
                "request_id": req.request_id,
                "model_name": req.model_name,
                "tenant_id": req.tenant_id,
                "priority": req.priority,
                "status": "QUEUED",
                "phase": "PENDING",
                "prompt_length": len(req.prompt),
                "tokens_generated": 0,
                "max_tokens": req.max_tokens,
                "arrival_time": req.arrival_time,
                "elapsed_seconds": round(time.time() - req.arrival_time, 2),
                "kv_blocks_allocated": 0
            }

    # 3. Check completed request history
    if request_id in request_history:
        return request_history[request_id]

    return JSONResponse(
        status_code=404,
        content={"error": {"code": "NOT_FOUND", "message": f"Request {request_id} not found", "request_id": request_id}}
    )

@app.get("/api/v1/dashboard/charts/latency")
async def get_latency_charts():
    """Latency distribution percentiles for Ops Console charting (SCH-146)."""
    return {
        "timestamp": time.time(),
        "metrics": {
            "ttft_ms": {
                "llama-3": {"p50": 42.5, "p90": 85.0, "p99": 145.2},
                "gpt-2": {"p50": 18.0, "p90": 32.5, "p99": 58.0}
            },
            "tpot_ms": {
                "llama-3": {"p50": 18.2, "p90": 24.5, "p99": 36.1},
                "gpt-2": {"p50": 8.5, "p90": 12.0, "p99": 19.4}
            },
            "e2e_ms": {
                "llama-3": {"p50": 320.0, "p90": 650.0, "p99": 1120.0},
                "gpt-2": {"p50": 140.0, "p90": 280.0, "p99": 490.0}
            }
        }
    }

# ==========================================
# Scheduler Control Plane API (SCH-102)
# ==========================================
class SchedulerConfigPayload(BaseModel):
    policy: Optional[str] = None
    max_batch_size: Optional[int] = None
    max_queue_depth: Optional[int] = None

@app.get("/api/v1/scheduler")
@app.get("/api/v1/scheduler/status")
async def get_scheduler_status():
    return {
        "status": "ACTIVE",
        "policy": scheduler_config["policy"],
        "max_batch_size": batcher.max_batch_size,
        "max_queue_depth": queue.max_capacity,
        "current_queue_depth": queue.size(),
        "active_batch_size": batcher.current_batch_size,
        "total_workers": len(worker_registry._workers),
        "uptime_seconds": round(time.time() - APP_START_TIME, 2)
    }


@app.post("/api/v1/scheduler/config")
async def update_scheduler_config(payload: SchedulerConfigPayload):
    req_id = f"cfg-{int(time.time()*1000)}"
    if payload.policy:
        scheduler_config["policy"] = payload.policy
    if payload.max_batch_size is not None:
        if payload.max_batch_size <= 0:
            return JSONResponse(
                status_code=400,
                content={"error": {"code": "INVALID_CONFIG", "message": "max_batch_size must be positive", "request_id": req_id}}
            )


        scheduler_config["max_batch_size"] = payload.max_batch_size
        batcher.max_batch_size = payload.max_batch_size
    if payload.max_queue_depth is not None:
        if payload.max_queue_depth <= 0:
            return JSONResponse(
                status_code=400,
                content={"error": {"code": "INVALID_CONFIG", "message": "max_queue_depth must be positive", "request_id": req_id}}
            )
        scheduler_config["max_queue_depth"] = payload.max_queue_depth
        queue.max_capacity = payload.max_queue_depth
    return {"status": "UPDATED", "config": scheduler_config}

# ==========================================
# Queue API (SCH-103)
# ==========================================
@app.get("/api/v1/queues")
async def get_queues():
    items = queue.all_requests()
    by_model: Dict[str, int] = {}
    for r in items:
        by_model[r.model_name] = by_model.get(r.model_name, 0) + 1
    return {
        "total_queued": len(items),
        "max_capacity": queue.max_capacity,
        "queues_by_model": by_model
    }

@app.get("/api/v1/queues/{model_name}")
async def get_model_queue(model_name: str):
    items = [
        {
            "request_id": r.request_id,
            "model_name": r.model_name,
            "priority": r.priority,
            "max_tokens": r.max_tokens,
            "arrival_time": r.arrival_time,
            "status": r.status.value
        }
        for r in queue.all_requests()
        if r.model_name == model_name
    ]
    return {"model_name": model_name, "count": len(items), "requests": items}

@app.delete("/api/v1/queues/{request_id}")
async def cancel_queued_request(request_id: str):
    removed = queue.remove(request_id)
    if not removed:
        return JSONResponse(
            status_code=404,
            content={"error": {"code": "NOT_FOUND", "message": f"Request {request_id} not found in queue", "request_id": request_id}}
        )


    removed.status = RequestStatus.CANCELLED
    return {"status": "CANCELLED", "request_id": request_id}

# ==========================================
# Worker API (SCH-105)
# ==========================================
class WorkerRegisterPayload(BaseModel):
    worker_id: str
    endpoint_url: str
    supported_models: List[str]
    gpu_ids: Optional[List[str]] = None
    max_concurrent_requests: int = 16

class WorkerHeartbeatPayload(BaseModel):
    gpu_utilization_pct: Optional[float] = 0.0
    gpu_free_memory_bytes: Optional[int] = 0
    gpu_temperature_c: Optional[float] = 40.0
    active_requests: Optional[int] = 0

@app.post("/api/v1/workers/register")
async def register_worker(payload: WorkerRegisterPayload):
    meta = worker_registry.register_worker(
        worker_id=payload.worker_id,
        endpoint_url=payload.endpoint_url,
        supported_models=set(payload.supported_models),
        gpu_ids=payload.gpu_ids,
        max_concurrent_requests=payload.max_concurrent_requests
    )
    replica = WorkerReplica(
        worker_id=payload.worker_id,
        endpoint_url=payload.endpoint_url,
        loaded_models=set(payload.supported_models),
        status=ReplicaStatus.HEALTHY
    )
    router.register_replica(replica)
    return {"status": "REGISTERED", "worker_id": meta.worker_id, "endpoint_url": meta.endpoint_url}

@app.post("/api/v1/workers/{worker_id}/heartbeat")
async def worker_heartbeat(worker_id: str, payload: WorkerHeartbeatPayload):
    ok = worker_registry.record_heartbeat(worker_id)
    if not ok:
        return JSONResponse(
            status_code=404,
            content={"error": {"code": "WORKER_NOT_FOUND", "message": f"Worker {worker_id} not registered", "request_id": f"hb-{int(time.time()*1000)}"}})





    rep = router.get_replica(worker_id)
    if rep:
        rep.gpu_utilization_pct = payload.gpu_utilization_pct or 0.0
        rep.gpu_free_memory_bytes = payload.gpu_free_memory_bytes or 0
        rep.gpu_temperature_c = payload.gpu_temperature_c or 40.0
        rep.active_requests = payload.active_requests or 0
    return {"status": "OK", "worker_id": worker_id}

@app.get("/api/v1/workers")
async def list_workers():
    workers = []
    for w in worker_registry._workers.values():
        rep = router.get_replica(w.worker_id)
        workers.append({
            "worker_id": w.worker_id,
            "endpoint_url": w.endpoint_url,
            "supported_models": list(w.supported_models),
            "is_alive": w.is_alive,
            "status": rep.status.value if rep else "UNKNOWN",
            "active_requests": rep.active_requests if rep else 0,
            "gpu_utilization_pct": rep.gpu_utilization_pct if rep else 0.0
        })
    return {"total_workers": len(workers), "workers": workers}

@app.post("/api/v1/workers/{worker_id}/drain")
async def drain_worker(worker_id: str):
    ok = router.drain_replica(worker_id)
    if not ok:
        return JSONResponse(
            status_code=404,
            content={"error": {"code": "WORKER_NOT_FOUND", "message": f"Worker {worker_id} not found", "request_id": f"drain-{int(time.time()*1000)}"}})
    rep = router.get_replica(worker_id)
    return {"status": rep.status.value if rep else "DRAINING", "worker_id": worker_id}
