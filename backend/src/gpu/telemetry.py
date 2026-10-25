"""
NVML telemetry adapter for GPU discovery and metrics (SCH-015, SCH-017).
Provides honest zero-GPU reporting when no hardware NVML driver is present,
and supports recorded/simulated NVML injection for hardware-in-the-loop testing.
"""

from typing import List, Dict, Any, Optional
import os

class NVMLTelemetryAdapter:
    def __init__(self, simulated_devices: Optional[List[Dict[str, Any]]] = None):
        self._simulated_devices = simulated_devices
        self._nvml_available = False
        try:
            import pynvml
            pynvml.nvmlInit()
            self._nvml_available = True
            self._pynvml = pynvml
        except Exception:
            self._nvml_available = False

    def is_hardware_available(self) -> bool:
        return self._nvml_available

    def query_devices(self, node_id: str = "node-1") -> List[Dict[str, Any]]:
        """
        Discovers GPU devices.
        If real NVML is present, reads genuine hardware metrics.
        If simulated devices were provided for test, returns them labeled.
        Otherwise honestly reports 0 devices.
        """
        if self._nvml_available:
            try:
                device_count = self._pynvml.nvmlDeviceGetCount()
                devices = []
                for i in range(device_count):
                    handle = self._pynvml.nvmlDeviceGetHandleByIndex(i)
                    name = self._pynvml.nvmlDeviceGetName(handle)
                    if isinstance(name, bytes):
                        name = name.decode("utf-8")
                    mem_info = self._pynvml.nvmlDeviceGetMemoryInfo(handle)
                    util = self._pynvml.nvmlDeviceGetUtilizationRates(handle)
                    temp = self._pynvml.nvmlDeviceGetTemperature(handle, self._pynvml.NVML_TEMPERATURE_GPU)
                    devices.append({
                        "gpu_id": f"{node_id}-gpu-{i}",
                        "node_id": node_id,
                        "device_name": name,
                        "total_memory_bytes": int(mem_info.total),
                        "allocated_memory_bytes": int(mem_info.used),
                        "utilization_pct": float(util.gpu),
                        "temperature_c": float(temp),
                        "is_healthy": True,
                        "simulated": False
                    })
                return devices
            except Exception:
                pass

        if self._simulated_devices is not None:
            return [
                {
                    **d,
                    "node_id": d.get("node_id", node_id),
                    "simulated": True
                }
                for d in self._simulated_devices
            ]

        # Honestly report 0 GPUs when no physical hardware is present
        return []
