from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any


class WorkloadType(StrEnum):
    AGENT = "agent"
    SCRIPT = "script"
    SERVICE = "service"


class RunMode(StrEnum):
    SCHEDULE = "schedule"
    FOREVER = "forever"
    N_TIMES = "n_times"


class WorkloadStatus(StrEnum):
    REGISTERED = "registered"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
    FAILED = "failed"
    COMPLETED = "completed"


@dataclass(frozen=True)
class WorkloadSpec:
    """Immutable specification loaded from YAML config."""

    name: str
    workload_type: WorkloadType
    run_mode: RunMode
    module_path: str
    entry_point: str = "run"
    schedule: str | None = None
    max_runs: int | None = None
    params: dict[str, Any] = field(default_factory=dict)
    restart_delay_seconds: float = 5.0
    timeout_seconds: float | None = None
    tags: list[str] = field(default_factory=list)
    version: str | None = None


@dataclass
class WorkloadState:
    """Mutable runtime state for a workload."""

    spec: WorkloadSpec
    status: WorkloadStatus = WorkloadStatus.REGISTERED
    pid: int | None = None
    run_count: int = 0
    last_started: datetime | None = None
    last_stopped: datetime | None = None
    last_heartbeat: datetime | None = None
    last_error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a dict suitable for JSON/API responses."""
        return {
            "name": self.spec.name,
            "type": self.spec.workload_type.value,
            "run_mode": self.spec.run_mode.value,
            "status": self.status.value,
            "pid": self.pid,
            "run_count": self.run_count,
            "last_started": self.last_started.isoformat() if self.last_started else None,
            "last_stopped": self.last_stopped.isoformat() if self.last_stopped else None,
            "last_error": self.last_error,
            "version": self.spec.version,
        }
