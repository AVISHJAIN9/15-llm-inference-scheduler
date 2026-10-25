"""
GPU Health Detection and Diagnostic Policy (SCH-016).
Monitors GPU operating parameters (temperature, uncorrectable ECC errors,
PCIe errors, driver health) and determines health status for scheduling.
"""

from enum import Enum
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field


class GPUHealthStatus(str, Enum):
    HEALTHY = "HEALTHY"
    OVERHEATED = "OVERHEATED"
    ECC_ERROR = "ECC_ERROR"
    DEGRADED = "DEGRADED"
    UNHEALTHY = "UNHEALTHY"


class GPUHealthPolicy(BaseModel):
    max_temperature_c: float = Field(default=85.0, description="Maximum allowable GPU temperature before overheating fault")
    max_ecc_errors: int = Field(default=0, description="Maximum allowable uncorrectable ECC memory errors")


class HealthCheckResult(BaseModel):
    gpu_id: str
    is_healthy: bool
    status: GPUHealthStatus
    reason: str


def evaluate_gpu_health(
    device_data: Dict[str, Any],
    policy: Optional[GPUHealthPolicy] = None
) -> HealthCheckResult:
    pol = policy or GPUHealthPolicy()
    gpu_id = device_data.get("gpu_id", "unknown")

    # Check ECC errors
    ecc_errors = int(device_data.get("ecc_errors", 0))
    if ecc_errors > pol.max_ecc_errors:
        return HealthCheckResult(
            gpu_id=gpu_id,
            is_healthy=False,
            status=GPUHealthStatus.ECC_ERROR,
            reason=f"Uncorrectable ECC memory error count ({ecc_errors}) exceeds limit ({pol.max_ecc_errors})"
        )

    # Check thermal limit
    temp = float(device_data.get("temperature_c", 0.0))
    if temp >= pol.max_temperature_c:
        return HealthCheckResult(
            gpu_id=gpu_id,
            is_healthy=False,
            status=GPUHealthStatus.OVERHEATED,
            reason=f"GPU temperature ({temp:.1f}°C) exceeds safety threshold ({pol.max_temperature_c:.1f}°C)"
        )

    # Check driver reported health
    driver_healthy = device_data.get("is_healthy", True)
    if not driver_healthy:
        return HealthCheckResult(
            gpu_id=gpu_id,
            is_healthy=False,
            status=GPUHealthStatus.UNHEALTHY,
            reason="Driver or telemetry reported GPU fault"
        )

    return HealthCheckResult(
        gpu_id=gpu_id,
        is_healthy=True,
        status=GPUHealthStatus.HEALTHY,
        reason="Operating normally within safety thresholds"
    )
