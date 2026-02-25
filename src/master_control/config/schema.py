from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, field_validator, model_validator

from master_control.models.workload import RunMode, WorkloadSpec


class FleetConfig(BaseModel):
    """Fleet communication settings for client daemons. All optional."""

    enabled: bool = False
    client_name: str | None = None
    api_host: str = "0.0.0.0"
    api_port: int = 9100
    central_api_url: str | None = None
    heartbeat_interval_seconds: float = 30.0
    api_token: str | None = None
    mdns_enabled: bool = False


class CentralConfig(BaseModel):
    """Central API server settings (control host only)."""

    enabled: bool = False
    host: str = "0.0.0.0"
    port: int = 8080
    db_path: str = "./fleet.db"
    inventory_path: str = "./inventory.yaml"
    api_token: str | None = None
    stale_threshold_seconds: float = 90.0
    deploy_script_path: str | None = None
    mdns_enabled: bool = False


class DaemonConfig(BaseModel):
    """Top-level daemon configuration loaded from daemon.yaml."""

    fleet: FleetConfig = FleetConfig()
    central: CentralConfig = CentralConfig()


class WorkloadConfig(BaseModel):
    """Pydantic model for validating a single workload YAML definition."""

    name: str
    type: str
    run_mode: Literal["schedule", "forever", "n_times"]
    module: str
    version: str | None = None
    entry_point: str = "run"
    schedule: str | None = None
    max_runs: int | None = None
    params: dict[str, Any] = {}
    restart_delay: float = 5.0
    timeout: float | None = None
    tags: list[str] = []
    memory_limit_mb: int | None = None
    cpu_nice: int | None = None

    @field_validator("memory_limit_mb")
    @classmethod
    def validate_memory_limit(cls, v: int | None) -> int | None:
        if v is not None and v <= 0:
            raise ValueError("'memory_limit_mb' must be a positive integer")
        return v

    @field_validator("cpu_nice")
    @classmethod
    def validate_cpu_nice(cls, v: int | None) -> int | None:
        if v is not None and not (-20 <= v <= 19):
            raise ValueError("'cpu_nice' must be between -20 and 19")
        return v

    @model_validator(mode="after")
    def validate_mode_fields(self) -> "WorkloadConfig":
        if self.run_mode == "schedule" and not self.schedule:
            raise ValueError("'schedule' field is required when run_mode is 'schedule'")
        if self.run_mode == "n_times" and not self.max_runs:
            raise ValueError("'max_runs' field is required when run_mode is 'n_times'")
        return self

    def to_spec(self) -> WorkloadSpec:
        return WorkloadSpec(
            name=self.name,
            workload_type=self.type,
            run_mode=RunMode(self.run_mode),
            module_path=self.module,
            entry_point=self.entry_point,
            schedule=self.schedule,
            max_runs=self.max_runs,
            params=self.params,
            restart_delay_seconds=self.restart_delay,
            timeout_seconds=self.timeout,
            tags=self.tags,
            version=self.version,
            memory_limit_mb=self.memory_limit_mb,
            cpu_nice=self.cpu_nice,
        )


class MultiWorkloadConfig(BaseModel):
    """Supports YAML files with a top-level 'workloads' list."""

    workloads: list[WorkloadConfig]
