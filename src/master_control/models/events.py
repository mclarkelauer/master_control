from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class WorkloadEvent:
    """An event emitted by the orchestrator about a workload."""

    workload_name: str
    event_type: str  # started, stopped, failed, completed, heartbeat
    payload: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)
