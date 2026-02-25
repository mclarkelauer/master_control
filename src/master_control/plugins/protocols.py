"""Plugin protocol definitions — contracts for workload types, health checks,
and log processors.

Plugin authors implement these protocols (no base class required) and register
them via Python entry points in their ``pyproject.toml``::

    [project.entry-points."master_control.workload_types"]
    container = "my_package.plugins:ContainerWorkloadType"

    [project.entry-points."master_control.health_checks"]
    http_check = "my_package.health:HttpHealthCheck"

    [project.entry-points."master_control.log_processors"]
    json_shipper = "my_package.logs:JsonLogShipper"
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from master_control.models.workload import WorkloadSpec, WorkloadState


@runtime_checkable
class WorkloadTypePlugin(Protocol):
    """Plugin that defines a custom workload type.

    Attributes:
        name: Unique identifier used in the ``type`` field of workload YAML
              (e.g., ``"container"``, ``"lambda"``).
    """

    name: str

    def validate_config(self, params: dict[str, Any]) -> None:
        """Validate workload-type-specific params. Raise ``ValueError`` on failure."""
        ...

    def build_launch_command(self, spec: WorkloadSpec) -> list[str]:
        """Return the subprocess command to launch this workload type.

        Return an empty list to fall back to the default ``_worker.py`` launcher.
        """
        ...


@runtime_checkable
class HealthCheckPlugin(Protocol):
    """Plugin that provides a custom health check.

    Attributes:
        name: Unique identifier for this health check.
    """

    name: str

    async def check(self, state: WorkloadState) -> dict[str, Any]:
        """Run a health check. Return ``{"healthy": bool, "details": ...}``."""
        ...


@runtime_checkable
class LogProcessorPlugin(Protocol):
    """Plugin that processes log lines from workloads.

    Attributes:
        name: Unique identifier for this log processor.
    """

    name: str

    async def process(self, workload_name: str, line: str) -> str | None:
        """Process a log line. Return the (possibly transformed) line, or
        ``None`` to drop it."""
        ...
