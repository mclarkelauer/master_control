"""Run mode strategies for workload supervision."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from master_control.models.workload import WorkloadSpec


class RunModeStrategy(Protocol):
    def should_restart(self, spec: WorkloadSpec, run_count: int, exit_code: int) -> bool: ...
    def is_complete(self, spec: WorkloadSpec, run_count: int) -> bool: ...


class ForeverStrategy:
    """Always restart after failure, unless explicitly stopped."""

    def should_restart(self, spec: WorkloadSpec, run_count: int, exit_code: int) -> bool:
        return True

    def is_complete(self, spec: WorkloadSpec, run_count: int) -> bool:
        return False


class NTimesStrategy:
    """Restart until run_count reaches max_runs."""

    def should_restart(self, spec: WorkloadSpec, run_count: int, exit_code: int) -> bool:
        return run_count < (spec.max_runs or 1)

    def is_complete(self, spec: WorkloadSpec, run_count: int) -> bool:
        return run_count >= (spec.max_runs or 1)


class ScheduleStrategy:
    """Single execution per trigger, no automatic restart."""

    def should_restart(self, spec: WorkloadSpec, run_count: int, exit_code: int) -> bool:
        return False

    def is_complete(self, spec: WorkloadSpec, run_count: int) -> bool:
        return True


def get_strategy(run_mode: str) -> RunModeStrategy:
    strategies: dict[str, RunModeStrategy] = {
        "forever": ForeverStrategy(),
        "n_times": NTimesStrategy(),
        "schedule": ScheduleStrategy(),
    }
    if run_mode not in strategies:
        raise ValueError(f"Unknown run mode: {run_mode}")
    return strategies[run_mode]
