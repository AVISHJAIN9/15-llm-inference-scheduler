"""
GPU Inventory, Memory Tracking, Health Detection, and Memory Admission Controller (SCH-015, SCH-016, SCH-017, SCH-024).
Persists device records to SQL database and coordinates memory capacity reservations.
"""

import uuid
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
from sqlalchemy import select, update, func
from sqlalchemy.ext.asyncio import AsyncSession
from gpu.models import GPUDeviceRecord, GPUDeviceSchema, GPUUtilizationRecord, GPUDeviceAssignmentRecord
from gpu.telemetry import NVMLTelemetryAdapter
from gpu.health import GPUHealthPolicy, GPUHealthStatus, HealthCheckResult, evaluate_gpu_health


class GPUManager:
    def __init__(self, session: AsyncSession, telemetry_adapter: Optional[NVMLTelemetryAdapter] = None):
        self.session = session
        self.telemetry = telemetry_adapter or NVMLTelemetryAdapter()

    async def sync_inventory(self, node_id: str = "node-1") -> List[GPUDeviceSchema]:
        """Queries telemetry and upserts discovered GPUs into the database (SCH-015)."""
        devices = self.telemetry.query_devices(node_id=node_id)
        synced = []

        for d in devices:
            stmt = select(GPUDeviceRecord).where(GPUDeviceRecord.gpu_id == d["gpu_id"])
            res = await self.session.execute(stmt)
            record = res.scalar_one_or_none()

            if record:
                record.device_name = d["device_name"]
                record.total_memory_bytes = d["total_memory_bytes"]
                record.allocated_memory_bytes = d["allocated_memory_bytes"]
                record.utilization_pct = d["utilization_pct"]
                record.temperature_c = d["temperature_c"]
                record.is_healthy = d.get("is_healthy", True)
                record.updated_at = datetime.now(timezone.utc)
            else:
                record = GPUDeviceRecord(
                    gpu_id=d["gpu_id"],
                    node_id=d["node_id"],
                    device_name=d["device_name"],
                    total_memory_bytes=d["total_memory_bytes"],
                    allocated_memory_bytes=d["allocated_memory_bytes"],
                    utilization_pct=d["utilization_pct"],
                    temperature_c=d["temperature_c"],
                    is_healthy=d.get("is_healthy", True),
                    health_status="HEALTHY",
                    health_reason="Initial registration",
                    updated_at=datetime.now(timezone.utc)
                )
                self.session.add(record)
            synced.append(record)

        await self.session.commit()
        return [self._to_schema(r) for r in synced]

    async def evaluate_and_update_health(
        self,
        policy: Optional[GPUHealthPolicy] = None,
        node_id: str = "node-1"
    ) -> List[HealthCheckResult]:
        """
        Evaluates GPU health against thresholds (temperature, ECC errors, driver health)
        and updates health status in the SQL database (SCH-016).
        """
        pol = policy or GPUHealthPolicy()
        telemetry_devices = {d["gpu_id"]: d for d in self.telemetry.query_devices(node_id=node_id)}
        stmt = select(GPUDeviceRecord)
        res = await self.session.execute(stmt)
        records = res.scalars().all()

        results: List[HealthCheckResult] = []
        now = datetime.now(timezone.utc)

        for rec in records:
            t_data = telemetry_devices.get(rec.gpu_id, {
                "gpu_id": rec.gpu_id,
                "temperature_c": rec.temperature_c,
                "is_healthy": rec.is_healthy,
                "ecc_errors": 0
            })
            result = evaluate_gpu_health(t_data, pol)
            rec.is_healthy = result.is_healthy
            rec.health_status = result.status.value
            rec.health_reason = result.reason
            rec.last_health_check_at = now
            rec.updated_at = now
            results.append(result)

        await self.session.commit()
        return results

    def _to_schema(self, r: GPUDeviceRecord) -> GPUDeviceSchema:
        return GPUDeviceSchema(
            gpu_id=r.gpu_id,
            node_id=r.node_id,
            device_name=r.device_name,
            total_memory_bytes=r.total_memory_bytes,
            allocated_memory_bytes=r.allocated_memory_bytes,
            utilization_pct=r.utilization_pct,
            temperature_c=r.temperature_c,
            is_healthy=r.is_healthy,
            health_status=r.health_status,
            health_reason=r.health_reason,
            last_health_check_at=r.last_health_check_at
        )

    async def list_devices(self) -> List[GPUDeviceSchema]:
        """Lists all registered GPUs (SCH-015)."""
        stmt = select(GPUDeviceRecord)
        res = await self.session.execute(stmt)
        records = res.scalars().all()
        return [self._to_schema(r) for r in records]

    async def get_device(self, gpu_id: str) -> Optional[GPUDeviceSchema]:
        """Gets device by ID with memory tracking (SCH-017)."""
        stmt = select(GPUDeviceRecord).where(GPUDeviceRecord.gpu_id == gpu_id)
        res = await self.session.execute(stmt)
        r = res.scalar_one_or_none()
        if not r:
            return None
        return self._to_schema(r)

    async def update_memory(self, gpu_id: str, delta_bytes: int) -> bool:
        """Atomically updates allocated memory on a GPU (SCH-017)."""
        stmt = select(GPUDeviceRecord).where(GPUDeviceRecord.gpu_id == gpu_id).with_for_update()
        res = await self.session.execute(stmt)
        record = res.scalar_one_or_none()
        if not record:
            return False

        new_allocated = record.allocated_memory_bytes + delta_bytes
        if new_allocated < 0 or new_allocated > record.total_memory_bytes:
            return False

        record.allocated_memory_bytes = new_allocated
        record.updated_at = datetime.now(timezone.utc)
        await self.session.commit()
        return True

    async def check_memory_admission(self, required_bytes: int, target_gpu_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Memory admission control (SCH-024).
        Verifies if target GPU (or any available healthy GPU) has sufficient free memory
        to safely admit the model / KV cache workload without triggering OOM.
        """
        stmt = select(GPUDeviceRecord).where(GPUDeviceRecord.is_healthy == True)
        if target_gpu_id:
            stmt = stmt.where(GPUDeviceRecord.gpu_id == target_gpu_id)

        res = await self.session.execute(stmt)
        candidates = res.scalars().all()

        for dev in candidates:
            free = dev.total_memory_bytes - dev.allocated_memory_bytes
            # Reserve a 5% safety margin against driver OOM
            safe_free = int(free * 0.95)
            if safe_free >= required_bytes:
                return {
                    "admitted": True,
                    "gpu_id": dev.gpu_id,
                    "required_bytes": required_bytes,
                    "available_bytes": free,
                    "safe_free_bytes": safe_free,
                    "reason": "Sufficient GPU memory available"
                }

        return {
            "admitted": False,
            "gpu_id": target_gpu_id,
            "required_bytes": required_bytes,
            "available_bytes": 0,
            "reason": "Insufficient GPU memory across available accelerators"
        }

    async def record_utilization_sample(
        self,
        gpu_id: str,
        compute_util_pct: float,
        memory_util_pct: float,
        temperature_c: Optional[float] = None,
        timestamp: Optional[datetime] = None
    ) -> GPUUtilizationRecord:
        """Records a point-in-time GPU utilization telemetry sample into SQL store (SCH-018)."""
        now = timestamp or datetime.now(timezone.utc)
        record = GPUUtilizationRecord(
            gpu_id=gpu_id,
            compute_util_pct=float(compute_util_pct),
            memory_util_pct=float(memory_util_pct),
            temperature_c=float(temperature_c) if temperature_c is not None else 0.0,
            timestamp=now
        )
        self.session.add(record)

        # Update latest telemetry on device record
        stmt = select(GPUDeviceRecord).where(GPUDeviceRecord.gpu_id == gpu_id)
        res = await self.session.execute(stmt)
        dev = res.scalar_one_or_none()
        if dev:
            dev.utilization_pct = float(compute_util_pct)
            if temperature_c is not None:
                dev.temperature_c = float(temperature_c)
            dev.updated_at = now

        await self.session.commit()
        return record

    async def get_utilization_history(self, gpu_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        """Returns chronological utilization telemetry samples for the given GPU (SCH-018)."""
        stmt = (
            select(GPUUtilizationRecord)
            .where(GPUUtilizationRecord.gpu_id == gpu_id)
            .order_by(GPUUtilizationRecord.timestamp.asc())
            .limit(limit)
        )
        res = await self.session.execute(stmt)
        records = res.scalars().all()
        return [r.to_dict() for r in records]

    async def get_utilization_summary(self, gpu_id: str) -> Dict[str, Any]:
        """Calculates aggregated utilization statistics (min, max, avg, sample count) (SCH-018)."""
        stmt = select(GPUUtilizationRecord).where(GPUUtilizationRecord.gpu_id == gpu_id)
        res = await self.session.execute(stmt)
        samples = res.scalars().all()

        if not samples:
            return {
                "gpu_id": gpu_id,
                "sample_count": 0,
                "min_compute_pct": 0.0,
                "max_compute_pct": 0.0,
                "avg_compute_pct": 0.0,
                "avg_memory_pct": 0.0
            }

        compute_vals = [s.compute_util_pct for s in samples]
        mem_vals = [s.memory_util_pct for s in samples]

        return {
            "gpu_id": gpu_id,
            "sample_count": len(samples),
            "min_compute_pct": min(compute_vals),
            "max_compute_pct": max(compute_vals),
            "avg_compute_pct": sum(compute_vals) / len(compute_vals),
            "avg_memory_pct": sum(mem_vals) / len(mem_vals)
        }

    async def assign_device(
        self,
        request_id: str,
        required_memory_bytes: int,
        target_gpu_id: Optional[str] = None,
        policy: str = "least_utilized"
    ) -> Optional[Dict[str, Any]]:
        """
        Assigns an inference workload to a healthy GPU (SCH-020).
        Validates target GPU health, checks memory headroom (with 5% safety margin),
        atomically updates device memory allocation, and creates an assignment record.
        """
        stmt = select(GPUDeviceRecord).where(GPUDeviceRecord.is_healthy == True)
        if target_gpu_id:
            stmt = stmt.where(GPUDeviceRecord.gpu_id == target_gpu_id)

        res = await self.session.execute(stmt)
        candidates = list(res.scalars().all())

        # Filter candidates that have sufficient headroom
        valid_candidates = []
        for dev in candidates:
            free = dev.total_memory_bytes - dev.allocated_memory_bytes
            safe_free = int(free * 0.95)
            if safe_free >= required_memory_bytes:
                valid_candidates.append(dev)

        if not valid_candidates:
            return None

        # Sort according to policy
        if policy == "least_utilized":
            valid_candidates.sort(key=lambda d: d.utilization_pct)
        elif policy == "most_free_memory":
            valid_candidates.sort(key=lambda d: d.total_memory_bytes - d.allocated_memory_bytes, reverse=True)

        chosen = valid_candidates[0]

        # Atomically update allocated memory
        chosen.allocated_memory_bytes += required_memory_bytes
        chosen.updated_at = datetime.now(timezone.utc)

        assignment_id = f"asgn-{uuid.uuid4().hex[:12]}"
        now = datetime.now(timezone.utc)
        record = GPUDeviceAssignmentRecord(
            assignment_id=assignment_id,
            gpu_id=chosen.gpu_id,
            request_id=request_id,
            allocated_memory_bytes=required_memory_bytes,
            status="ASSIGNED",
            assigned_at=now
        )
        self.session.add(record)
        await self.session.commit()

        return {
            "assignment_id": assignment_id,
            "gpu_id": chosen.gpu_id,
            "request_id": request_id,
            "allocated_memory_bytes": required_memory_bytes,
            "status": "ASSIGNED"
        }

    async def release_device_assignment(self, assignment_id: str) -> bool:
        """Releases an active device assignment and restores GPU memory capacity (SCH-020)."""
        stmt = select(GPUDeviceAssignmentRecord).where(GPUDeviceAssignmentRecord.assignment_id == assignment_id)
        res = await self.session.execute(stmt)
        assignment = res.scalar_one_or_none()
        if not assignment or assignment.status == "RELEASED":
            return False

        # Find GPU and restore memory
        gpu_stmt = select(GPUDeviceRecord).where(GPUDeviceRecord.gpu_id == assignment.gpu_id)
        gpu_res = await self.session.execute(gpu_stmt)
        gpu = gpu_res.scalar_one_or_none()
        if gpu:
            gpu.allocated_memory_bytes = max(0, gpu.allocated_memory_bytes - assignment.allocated_memory_bytes)
            gpu.updated_at = datetime.now(timezone.utc)

        assignment.status = "RELEASED"
        assignment.released_at = datetime.now(timezone.utc)
        await self.session.commit()
        return True


