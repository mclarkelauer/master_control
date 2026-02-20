from typing import Any, Literal

from pydantic import BaseModel, model_validator

from master_control.models.workload import RunMode, WorkloadSpec, WorkloadType


class WorkloadConfig(BaseModel):
    """Pydantic model for validating a single workload YAML definition."""

    name: str
    type: Literal["agent", "script", "service"]
    run_mode: Literal["schedule", "forever", "n_times"]
    module: str
    entry_point: str = "run"
    schedule: str | None = None
    max_runs: int | None = None
    params: dict[str, Any] = {}
    restart_delay: float = 5.0
    timeout: float | None = None
    tags: list[str] = []

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
            workload_type=WorkloadType(self.type),
            run_mode=RunMode(self.run_mode),
            module_path=self.module,
            entry_point=self.entry_point,
            schedule=self.schedule,
            max_runs=self.max_runs,
            params=self.params,
            restart_delay_seconds=self.restart_delay,
            timeout_seconds=self.timeout,
            tags=self.tags,
        )


class MultiWorkloadConfig(BaseModel):
    """Supports YAML files with a top-level 'workloads' list."""

    workloads: list[WorkloadConfig]
