"""Health checker — periodically verifies workload processes are alive."""

from __future__ import annotations

import asyncio
import os
from typing import TYPE_CHECKING

import structlog

from master_control.models.workload import WorkloadStatus

if TYPE_CHECKING:
    from master_control.engine.orchestrator import Orchestrator

log = structlog.get_logger()


def collect_system_metrics() -> dict[str, float]:
    """Collect system-level resource metrics. Uses psutil if available, falls back to /proc."""
    try:
        import psutil

        mem = psutil.virtual_memory()
        disk = psutil.disk_usage("/")
        return {
            "cpu_percent": psutil.cpu_percent(interval=0.1),
            "memory_used_mb": round((mem.total - mem.available) / (1024 * 1024), 1),
            "memory_total_mb": round(mem.total / (1024 * 1024), 1),
            "disk_used_gb": round(disk.used / (1024**3), 2),
            "disk_total_gb": round(disk.total / (1024**3), 2),
        }
    except ImportError:
        return _collect_metrics_from_proc()


def _collect_metrics_from_proc() -> dict[str, float]:
    """Fallback metrics collection from /proc filesystem."""
    metrics: dict[str, float] = {
        "cpu_percent": 0.0,
        "memory_used_mb": 0.0,
        "memory_total_mb": 0.0,
        "disk_used_gb": 0.0,
        "disk_total_gb": 0.0,
    }
    try:
        with open("/proc/meminfo") as f:
            meminfo = {}
            for line in f:
                parts = line.split(":")
                if len(parts) == 2:
                    key = parts[0].strip()
                    val = parts[1].strip().split()[0]
                    meminfo[key] = int(val)
            total_kb = meminfo.get("MemTotal", 0)
            avail_kb = meminfo.get("MemAvailable", 0)
            metrics["memory_total_mb"] = round(total_kb / 1024, 1)
            metrics["memory_used_mb"] = round((total_kb - avail_kb) / 1024, 1)
    except (OSError, ValueError, KeyError):
        pass

    try:
        stat = os.statvfs("/")
        total = stat.f_blocks * stat.f_frsize
        free = stat.f_bfree * stat.f_frsize
        metrics["disk_total_gb"] = round(total / (1024**3), 2)
        metrics["disk_used_gb"] = round((total - free) / (1024**3), 2)
    except OSError:
        pass

    return metrics


class HealthChecker:
    """Periodically checks each running workload's process is alive."""

    def __init__(self, orchestrator: Orchestrator, interval: float = 10.0) -> None:
        self._orchestrator = orchestrator
        self._interval = interval
        self._task: asyncio.Task | None = None
        self._running = False

    async def start(self) -> None:
        self._running = True
        self._task = asyncio.create_task(self._run())
        log.info("health checker started", interval=self._interval)

    async def stop(self) -> None:
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _run(self) -> None:
        try:
            while self._running:
                await self._check_all()
                await asyncio.sleep(self._interval)
        except asyncio.CancelledError:
            pass

    async def _check_all(self) -> None:
        for state in self._orchestrator.list_workloads():
            if state.status != WorkloadStatus.RUNNING:
                continue
            if state.pid is None:
                continue
            if not self._is_process_alive(state.pid):
                log.warning(
                    "health check failed: process not found",
                    workload=state.spec.name,
                    pid=state.pid,
                )
                state.status = WorkloadStatus.FAILED
                state.last_error = f"Process {state.pid} not found"
                continue

            if state.spec.memory_limit_mb is not None:
                self._check_memory_usage(state)

    @staticmethod
    def _check_memory_usage(state) -> None:
        """Log a warning if a workload's RSS approaches its memory limit."""
        try:
            import psutil

            proc = psutil.Process(state.pid)
            rss_mb = proc.memory_info().rss / (1024 * 1024)
            threshold = state.spec.memory_limit_mb * 0.9
            if rss_mb >= threshold:
                log.warning(
                    "workload approaching memory limit",
                    workload=state.spec.name,
                    rss_mb=round(rss_mb, 1),
                    limit_mb=state.spec.memory_limit_mb,
                )
        except ImportError:
            pass
        except Exception:
            pass

    @staticmethod
    def _is_process_alive(pid: int) -> bool:
        try:
            os.kill(pid, 0)
            return True
        except ProcessLookupError:
            return False
        except PermissionError:
            # Process exists but we can't signal it
            return True
