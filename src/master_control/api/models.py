"""Pydantic models shared between client and central APIs."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class WorkloadInfo(BaseModel):
    """Workload state as reported by a client daemon."""

    name: str
    type: str
    run_mode: str
    status: str
    pid: int | None = None
    run_count: int = 0
    last_started: str | None = None
    last_error: str | None = None


class SystemMetrics(BaseModel):
    """System-level resource metrics from a client."""

    cpu_percent: float = 0.0
    memory_used_mb: float = 0.0
    memory_total_mb: float = 0.0
    disk_used_gb: float = 0.0
    disk_total_gb: float = 0.0


class HeartbeatPayload(BaseModel):
    """Payload sent by client daemons to the central API."""

    client_name: str
    timestamp: datetime
    workloads: list[WorkloadInfo] = []
    system: SystemMetrics = SystemMetrics()


class ClientOverview(BaseModel):
    """Summary of a client as seen by the central API."""

    name: str
    host: str
    api_port: int = 9100
    status: str = "unknown"  # online, offline, stale
    last_seen: datetime | None = None
    workload_count: int = 0
    workloads_running: int = 0
    workloads_failed: int = 0
    system: SystemMetrics | None = None


class CommandResponse(BaseModel):
    """Generic response for command operations."""

    success: bool
    message: str
